try:
  import json
except ImportError:
  from django.utils import simplejson as json

from collections import OrderedDict
import logging
import traceback
import __future__

from stochssapp import BaseHandler
from stochss.backendservice import *

class 

class CredentialsPage(BaseHandler):
    """
    Provides a web UI around POST /model, to allow users to create
    StochKitModelWrappers via the web interface instead of the RESTful one.
    """    
    def get(self):
        try:
            # User id is a numeric value.
            user_id = self.user.user_id()
            if user_id is None:
                raise InvalidUserException
        except Exception, e:
            raise InvalidUserException('Cannot determine the current user. '+str(e))
                
        all_vms = self.get_all_vms(user_id)
        context = {'vm_names':all_vms, 'number_of_vms':len(all_vms)}
        self.render_response('credentialspage.html', **context)
        

    def post(self):
        # First, check to see if it's a save_changes request and then route it to the appropriate function.
        save_changes = self.request.get('save')
        
        """ if save is not "":
            result = self.save_credentials(save_changes)        
            result = dict(get_all_vms(self), **result)
            self.render_response('credentialspage.html', **result)   
        elif start:
            result = self.start_vm()
            result = dict(get_all_vms(self), **result)
            self.render_response('credentialspage.html', **result)                                 
        else delete:
            result = self.delete_vms() 
            result = dict(get_all_vms(self), **result)
            self.render_response('credentialspage.html', **result)    """                      
            
    def get_all_vms(self,user):
        """

        """
        #bs = Backendservice()
        #valid_username = self.get_session_property('username')
        if user is None or user is "":
            return None
        else:
            result = ["VM1", "VM2", "VM3"]
            #result = bs.describeMachines(user)
        return result
        #self.render_response('credentialspage.html', **result)
        
	def save_credentials(self, save_changes):
		"""
		Save the Credentials
		""" 
       # Flush the data in cache to the datastore.
        db_user = db.GqlQuery("SELECT * FROM StochKitModelWrapper WHERE user_id = :1", user_id).get()
        db_user.user = valid_username
        db_user.put()
        result = {'status': True, 'msg': model.name + ' saved successfully!'}		

class InvalidUserException(Exception):
    pass
