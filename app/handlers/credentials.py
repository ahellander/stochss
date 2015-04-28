try:
  import json
except ImportError:
  from django.utils import simplejson as json

from collections import OrderedDict
import logging

import __future__
import random
import string
from stochssapp import BaseHandler
from backend.backendservice import *
from google.appengine.ext import db

import os
import re
import pprint
import time

from backend.common.config import AWSConfig, AgentTypes, AgentConfig
from backend.databases.dynamo_db import DynamoDB

class CredentialsPage(BaseHandler):
    INS_TYPES = ["t1.micro", "m1.small", "m3.medium", "m3.large", "c3.large", "c3.xlarge"]
    HEAD_NODE_TYPES = ["c3.large", "c3.xlarge"]
    
    def authentication_required(self):
        return True
    
    def get(self):
        try:
            # User id is a string
            user_id = self.user.user_id()
            if user_id is None:
                raise InvalidUserException
        except Exception, e:
            raise InvalidUserException('Cannot determine the current user. '+str(e))
        
        context = self.getContext(user_id)
        self.render_response('credentials.html', **context)


    def post(self):
        logging.info("request.body = {0}".format(self.request.body))
        logging.info("CONTENT_TYPE = {0}".format(self.request.environ['CONTENT_TYPE']))
        
        try:
            # User id is a string
            user_id = self.user.user_id()
            if user_id is None:
                raise InvalidUserException
        except Exception, e:
            raise InvalidUserException('Cannot determine the current user. '+str(e))

        if re.match('^application/json.*', self.request.environ['CONTENT_TYPE']):
            data_received = json.loads(self.request.body)
            logging.info("json data = \n{0}".format(pprint.pformat(data_received)))

            if data_received['action'] == 'save_flex_cloud_info':
                machine_info = data_received['flex_cloud_machine_info']
                logging.info("machine_info = \n{0}".format(pprint.pformat(machine_info)))

                result = self.save_flex_cloud_info(machine_info)
                logging.info("result = {0}".format(result))

                # TODO: This is a hack to make it unlikely that the db transaction has not completed
                # before we re-render the page (which would cause an error). We need some real solution for this...
                time.sleep(0.5)

                context = self.getContext(user_id)
                logging.info('{0}'.format(dict(context, **result)))
                self.render_response('credentials.html', **(dict(context, **result)))

            elif data_received['action'] == 'prepare_flex_cloud':
                credentials = self.user_data.getCredentials()
                flex_cloud_machine_info = self.user_data.get_flex_cloud_machine_info()

                head_node = None
                for machine in flex_cloud_machine_info:
                    if machine['queue_head'] == True:
                        head_node = machine
                        head_node['instance_type'] = None

                result = self.prepare_flex_cloud(user_id, credentials, head_node, flex_cloud_machine_info)
                logging.info("result = {0}".format(result))

                context = self.getContext(user_id)
                self.render_response('credentials.html', **(dict(context, **result)))

            else:
                result = {'status': True, 'msg': ''}
                context = self.getContext(user_id)
                self.render_response('credentials.html', **(dict(context, **result)))

        else:
            params = self.request.POST

            if 'save' in params:
                # Save the access and private keys to the datastore
                access_key = params['ec2_access_key']
                secret_key = params['ec2_secret_key']

                credentials = {'EC2_ACCESS_KEY':access_key, 'EC2_SECRET_KEY':secret_key}
                result = self.saveCredentials(credentials)
                # TODO: This is a hack to make it unlikely that the db transaction has not completed
                # before we re-render the page (which would cause an error). We need some real solution for this...
                time.sleep(0.5)

                self.redirect('/credentials')

            elif 'start' in params:
                context = self.getContext(user_id)
                vms = []
                all_numbers_correct = True

                if 'compute_power' in params:
                    if params['compute_power'] == 'small':
                         head_node = {"instance_type": 'c3.large', "num_vms": 1}
                    else:
                        result = {'status': False , 'msg': 'Unknown instance type.'}
                        all_numbers_correct = False
                else:
                    head_node = None
                    if 'head_node' in params:
                        head_node = {"instance_type": params['head_node'].replace('radio_', ''), "num_vms": 1}

                    for type in self.INS_TYPES:
                        num_type = 'num_'+type

                        if num_type in params and params[num_type] != '':
                            if int(params[num_type]) > 20:
                                result = {'status': False , 'msg': 'Number of new vms should be no more than 20.'}
                                all_numbers_correct = False
                                break
                            elif int(params[num_type]) <= 0:
                                result = {'status': False , 'msg': 'Number of new vms should be at least 1.'}
                                all_numbers_correct = False
                                break
                            else:
                                vms.append({"instance_type": type, "num_vms": int(params[num_type])})
                active_nodes = context['number_creating'] + context['number_pending'] + context['number_running']

                if all_numbers_correct:
                    result = self.start_vms(user_id, self.user_data.getCredentials(), head_node, vms, active_nodes)
                    context['starting_vms'] = True
                else:
                    context['starting_vms'] = False

                self.redirect('/credentials');

            elif 'stop' in params:
                # Kill all running VMs.
                try:
                    service = backendservices()
                    credentials = self.user_data.getCredentials()
                    terminate_params = {
                      "infrastructure": "ec2",
                      "credentials": self.user_data.getCredentials(),
                      "key_prefix": user_id
                    }
                    stopped = service.stopMachines(terminate_params,True) #True means blocking, ie wait for success (its pretty quick)
                    if not stopped:
                        raise
                    result = {'status': True, 'msg': 'Successfully terminated all running VMs.'}
                except Exception,e:
                    result = {'status': False, 'msg': 'Failed to terminate the VMs. Please check their status in the EC2 managment console available from your Amazon account.'}
                    context = self.getContext(user_id)
                    self.render_response('credentials.html',**(dict(context,**result)))
                    return

                self.redirect('/credentials');

            else: # This happens when you click the refresh button
                self.redirect('/credentials')

    def save_flex_cloud_info(self, machine_info):
        try:
            if backendservices.validate_flex_cloud_info(machine_info):
                self.user_data.valid_flex_cloud_info = True
                result = {'flex_cloud_status': True,
                          'flex_cloud_info_msg': 'Flex Cloud machine info has been successfully validated!'}
            else:
                self.user_data.valid_flex_cloud_info = False
                result = {'flex_cloud_status': False,
                          'flex_cloud_info_msg': 'Invalid Flex Cloud machine info!'}

            self.user_data.set_flex_cloud_machine_info(machine_info)
            self.user_data.put()

        except Exception, e:
            logging.error(e.message)
            result = {'status': False,
                      'flex_cloud_info_msg': 'Invalid Flex Cloud machine info!'}

        return result

    def saveCredentials(self, credentials, database=None):
        """ Save the Credentials to the datastore. """
        try:
            service = backendservices()
            params ={}
            params['credentials'] =credentials
            params["infrastructure"] = "ec2"
            
            # Check if the supplied credentials are valid of not
            if service.validateCredentials(params):
                self.user_data.valid_credentials = True
                result = {'status': True, 'credentials_msg': ' Credentials saved successfully! The EC2 keys have been validated.'}
                # See if the amazon db table is intitalized
                if not self.user_data.isTable():
                    db_credentials = self.user_data.getCredentials()
                    # Set the environmental variables
                    os.environ["AWS_ACCESS_KEY_ID"] = credentials['EC2_ACCESS_KEY']
                    os.environ["AWS_SECRET_ACCESS_KEY"] = credentials['EC2_SECRET_KEY']

                    try:
                        if not database:
                            database = DynamoDB(os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"])
                            
                        database.createtable(backendservices.STOCHSS_TABLE)
                        database.createtable(backendservices.COST_ANALYSIS_TABLE)
                        self.user_data.is_amazon_db_table=True
                    except Exception,e:
                        pass
            else:
                result = {'status': False, 'credentials_msg':' Invalid Secret Key or Access key specified'}
                self.user_data.valid_credentials = False
    
            # Write the credentials to the datastore
            self.user_data.setCredentials(credentials)
            self.user_data.put()
        
    
        except Exception,e:
            result = {'status': False, 'credentials_msg':' There was an error saving the credentials: '+str(e)}
        
        return result

    def prepare_flex_cloud(self, user_id, credentials, head_node, flex_cloud_machine_info):
        logging.info('head_node = \n{0}'.format(pprint.pformat(head_node)))
        params = {
            'infrastructure': 'flex',
            'flex_cloud_machine_info': flex_cloud_machine_info,
            'key_prefix': '', # no prefix
            'keyname': '',
            'email': [user_id],
            'credentials': credentials,
            'head_node': head_node
        }

        service = backendservices(infrastructure=AgentTypes.FLEX)

        if not service.isOneOrMoreComputeNodesRunning(params):
            if head_node is None:
                return {'status': 'Failure',
                        'msg': "At least one head node needs to be ready."}
            else:
                params['head_node'] = head_node

        elif head_node:
            params['vms'] = [head_node]

        res, msg = service.prepare_flex_cloud_machines(params)
        if res == True:
            result = {'status': 'Success',
                      'msg': 'Successfully prepared flex cloud machines.'}
        else:
            result = {'status': 'Failure',
                      'msg': msg}
        return result

    def getContext(self, user_id):
        params = {}
        credentials =  self.user_data.getCredentials()

        flex_cloud_machine_info = self.user_data.get_flex_cloud_machine_info()
        logging.info("flex_cloud_machine_info =\n{0}".format(pprint.pformat(flex_cloud_machine_info)))

        params['credentials'] = credentials
        
        context = {}
        result = {}

        # EC2
        # Check if the credentials are valid.
        params["infrastructure"] = "ec2"

        if not self.user_data.valid_credentials:
            result = {'status': False,
                      'vm_status': False,
                      'vm_status_msg': 'Could not determine the status of the VMs: Invalid Credentials!'}

            context['vm_names'] = None
            context['valid_credentials']=False
            context['active_vms']=False

            fake_credentials = { 'EC2_ACCESS_KEY': '',
                                 'EC2_SECRET_KEY': ''}
        else:
            fake_credentials = { 'EC2_ACCESS_KEY': '*' * len(credentials['EC2_ACCESS_KEY']),
                                 'EC2_SECRET_KEY': '*' * len(credentials['EC2_SECRET_KEY'])}
            context['valid_credentials'] = True

            all_vms = self.get_all_vms(user_id, params)

            if all_vms == None:
                result = {'status': False,
                          'vm_status': False,
                          'vm_status_msg': 'Could not determine the status of the VMs.'}

                context = {'vm_names':all_vms}
            else:
                number_creating = 0
                number_pending = 0
                number_running = 0
                number_failed = 0
                running_instances = {}

                for vm in all_vms:
                    if vm != None and vm['state']=='creating':
                        number_creating += 1
                    elif vm != None and vm['state']=='pending':
                        number_pending += 1
                    elif vm != None and vm['state']=='running': 
                        number_running += 1
                        instance_type = vm['instance_type']
                        if instance_type not in running_instances:
                            running_instances[instance_type] = 1
                        else:
                            running_instances[instance_type] = running_instances[instance_type] + 1
                    elif vm != None and vm['state']=='failed':
                        number_failed += 1

                number_of_vms = len(all_vms)

                logging.info("number creating = {0}".format(number_creating))
                logging.info("number pending = {0}".format(number_pending))
                logging.info("number running = {0}".format(number_running))
                logging.info("number failed = {0}".format(number_failed))

                context['number_of_vms'] = number_of_vms
                context['vm_names'] = all_vms
                context['number_creating'] = number_creating
                context['number_pending'] = number_pending
                context['number_running'] = number_running
                context['number_failed'] = number_failed
                context['running_instances'] = running_instances

                result['status']= True
                result['credentials_msg'] = 'The EC2 keys have been validated.'
                if number_running+number_pending+number_creating+number_failed == 0:
                    context['active_vms'] = False
                else:
                    context['active_vms'] = True
                    
                if number_running == 0:
                    context['running_vms'] = False
                else:
                    context['running_vms'] = True

        # Check if the flex cloud credentials are valid.
        if not self.user_data.valid_flex_cloud_info:
            result['flex_cloud_status'] = False
            result['flex_cloud_info_msg'] = 'Could not determine the status of the machines: Invalid Flex Cloud Credentials!'
            context['valid_flex_cloud_info'] = False
        else:
            context['flex_cloud_machine_info'] = json.dumps(flex_cloud_machine_info)
            context['valid_flex_cloud_info'] = True
                
        context = dict(context, **fake_credentials)
        context = dict(result, **context)
        return context
    
    def get_all_vms(self, user_id, params):
        """
            
        """
        if user_id is None or user_id is "":
            return None
        else:
            try:
                service = backendservices()
                result = service.describeMachinesFromDB(params)
                return result
            except:
                return None
                    
    def start_vms(self, user_id, credentials, head_node, vms_info, active_nodes):
        key_prefix = AgentConfig.get_agent_key_prefix(AgentTypes.EC2, key_prefix=user_id)
        group_random_name = AgentConfig.get_random_group_name(prefix=key_prefix)

        logging.debug("key_prefix = {0}".format(key_prefix))
        logging.debug("group_random_name = {0}".format(group_random_name))

        params ={
            "infrastructure": AgentTypes.EC2,
            'group': group_random_name,
            'vms': vms_info,
            'image_id': None,
            'key_prefix': key_prefix,
            'keyname': group_random_name,
            'email': [user_id],
            'credentials': credentials,
            'use_spot_instances' :False
        }

        # Check for AMI build by the stochss_ami_manager
        try:
            with open(AWSConfig.EC2_SETTINGS_FILENAME) as fd:
                ec2_config = json.load(fd)
                params['image_id'] = ec2_config['ami_id']
        except Exception as e:
            logging.error(e)
            return {
                'status':False,
                'msg': 'Cannot load AMI config from {0}!'.format(AWSConfig.EC2_SETTINGS_FILENAME)
            }

        service = backendservices()
        
        if active_nodes == 0:
            if head_node is None:
                return {'status':False , 'msg': "At least one head node needs to be launched."} 
            else:
                params['head_node'] = head_node
                
        elif head_node:
            params['vms'] = [head_node]
                      
        res, msg = service.startMachines(params)
        if res == True:
            result = {
                'status':True,
                'msg': 'Successfully requested starting virtual machines. Processing request...'
            }
        else:
            result = {
                'status':False,
                'msg': msg
            }

        return result



class LocalSettingsPage(BaseHandler):
    """ Set paths for local plugin software. """
    def authentication_required(self):
        return True
    
    def get(self):
        """ """
        env_variables = self.user_data.env_variables
        if env_variables == None:
            context = {}
        else:
            context = json.loads(env_variables)
        
        logging.info(context)
        self.render_response("localsettings.html",**context)
    
    def post(self):
        """ """
        params = self.request.POST
        
        if self.user_data.env_variables == None:
            env_variables = {}
        else:
            env_variables = json.loads(self.user_data.env_variables)
                
        for key in params:
            env_variables[key] = params[key]
                
        self.user_data.env_variables = json.dumps(env_variables)
        self.user_data.put()
        self.render_response("localsettings.html",**env_variables)


class InvalidUserException(Exception):
    pass
