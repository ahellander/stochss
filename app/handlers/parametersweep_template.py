import gillespy
import json
import molnsutil
import numpy

### NOTE the string '___JSON_STRING___' will be replaced by data from the model

class StochSSModel(gillespy.Model):
    json_data = json.loads("""___JSON_STRING___""")
    def __init__(self, **kwargs):
        modelType = self.json_data["modelType"]
        species = self.json_data["species"]
        parameters = self.json_data["parameters"]
        reactions = self.json_data["reactions"]
        maxTime = self.json_data["maxTime"]
        if maxTime is None:
            maxTime = 100
        increment = self.json_data["increment"]
        if increment is None:
            increment = 1


        gillespy.Model.__init__(self, name = self.json_data["name"])

        parameterByName = dict()

        for parameter in parameters:
            if parameter['name'] in kwargs:
                parameterByName[parameter['name']] = gillespy.Parameter(name = parameter['name'], expression = kwargs[parameter['name']])
            else:
                parameterByName[parameter['name']] = gillespy.Parameter(name = parameter['name'], expression = parameter['value'])

            self.add_parameter(parameterByName[parameter['name']])

        speciesByName = dict()

        for specie in species:
            speciesByName[specie['name']] = gillespy.Species(name = specie['name'], initial_value = specie['initialCondition'])

            self.add_species(speciesByName[specie['name']])

        for reaction in reactions:
            inReactants = dict()
            for reactant in reaction['reactants']:
                if reactant['specie'] not in inReactants:
                    inReactants[reactant['specie']] = 0

                inReactants[reactant['specie']] += reactant['stoichiometry']

            inProducts = dict()
            for product in reaction['products']:
                if product['specie'] not in inProducts:
                    inProducts[product['specie']] = 0

                inProducts[product['specie']] += product['stoichiometry']

            reactants = dict([(speciesByName[reactant[0]], reactant[1]) for reactant in inReactants.items()])

            products = dict([(speciesByName[product[0]], product[1]) for product in inProducts.items()])
            
            if(reaction['type'] == 'custom'):
                self.add_reaction(gillespy.Reaction(name = reaction['name'], reactants = reactants, products = products, propensity_function = reaction['equation']))
            else:
                self.add_reaction(gillespy.Reaction(name = reaction['name'], reactants = reactants, products = products, rate = parameterByName[reaction['rate']]))

        self.timespan(numpy.concatenate((numpy.arange(maxTime / increment) * increment, [maxTime])))


#model = Model()
#output = model.run()
#print output


funcA = numpy.linspace if StochSSModel.json_data['logA'] else numpy.logspace
funcB = numpy.linspace if StochSSModel.json_data['logB'] else numpy.logspace

parameters = dict()

parameters[StochSSModel.json_data['parameterA']] = funcA(StochSSModel.json_data['minValueA'], StochSSModel.json_data['maxValueA'], StochSSModel.json_data['stepsA'])

if StochSSModel.json_data['variableCount'] != 1:
    parameters[StochSSModel.json_data['parameterB']] = funcB(StochSSModel.json_data['minValueB'], StochSSModel.json_data['maxValueB'], StochSSModel.json_data['stepsB'])

print "Parameters: ",parameters

import uuid
name = "StochSS_exec" + str(uuid.uuid4())
print "Name: ", name
import sys
sys.stdout.flush()

sweep = molnsutil.ParameterSweep(name=name, model_class=StochSSModel, parameters=parameters)
#sweep = molnsutil.ParameterSweep(model_class=StochSSModel, parameters=parameters)

def mapAnalysis(result):
    #mappedResults = dict()
    #for i, specie in enumerate(species):
    #    mappedResults['maxVal'] = numpy.max(results[:, i + 1, :])
    return result.shape#mappedResults

sys.stdout.write("Starting Parameter sweep\n")
sys.stdout.flush()
ret = sweep.run(mapper = mapAnalysis, number_of_trajectories = 1, chunk_size = 1, store_realizations = False, progress_bar = False)

import pickle
dat = []
for r in ret:
    dat.append({'parameters':r.parameters, 'result':r.result})
with open('results', 'w') as f:
    pickle.dump(dat, f)
