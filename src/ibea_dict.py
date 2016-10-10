#!/usr/bin/env python2
# -*- coding : utf8 -*-

""" Indicator-based Evolutionary Algorithm with Epsilon indicator
is an evolutionary algorithm for searching a multi-objective space using the concept of the Pareto front.
Formally, the algorithm is classified as a (\mu/\rho + \lambda)-ES.
Indeed, the \lambda offsprings are produced by \rho mates selected from \mu after a binary tournament.
An Evolution Strategy which applies `+` selection takes fitness into account for the selection phase.
"""
from __future__ import division
from operator import mod
from numpy import sqrt, power, exp, float64, infty
from numpy import array, empty, divide, minimum, maximum
from numpy.random import seed, choice, binomial
from numpy.random import rand, randint, randn
from collections import deque

from crossovers import bounded_sbx

class IBEA(object):
    def __init__(self,
                 kappa=0.05, 
                 alpha=100, 
                 n_offspring=8, 
                 seedit=42,
                 pr_x=1.0, # 0.5
                 pr_mut=0.01, # 0.8
                 var=0.1): # \in [0, 0.1]
        # --- Algorithm parameters
        self.kappa = kappa             # Fitness scaling ratio
        self.alpha = alpha             # Population size
        self.pr_crossover = pr_x       # Crossover probability
        self.pr_mutation = pr_mut      # Mutation probability
        self.noise_variance = var      # Noise level for mutation
        self.n_offspring = n_offspring # Number of offspring individuals
        self._min = None               # Objective function minima
        self._max = None               # Objective function maxima
        self.indicator_max = None      # Indicator function maximum

        # --- Data structure containing: population vectors, fitness and objective values
        self.pop_data = dict()
        # --- Free indices for the population dictionary
        self.free_indices = deque()
        # --- Population counter
        self.population_size = 0

        # --- Random state
        seed(seedit)

    def __str__(self):
        #return 'Indicator-based Evolutionary Algorithm with Epsilon indicator'
        return 'ibea_pop{}_offs{}_mut{}_recomb{}_var{}'.format(self.alpha, self.n_offspring,
                                                           self.pr_mutation, self.pr_crossover,
                                                           self.noise_variance)
    def ibea(self, fun, lbounds, ubounds, budget):
        lbounds, ubounds = array(lbounds), array(ubounds) # [-100, 100]
        dim, f_min = len(lbounds), None
        dim_sqrt = sqrt(dim+1)
        # Pr(mutation) = 1/n
        self.pr_mutation = 1/dim
        
        # 1. Initial population of size alpha
        # Sampled from the uniform distribution [lbounds, ubounds]
        particles = rand(self.alpha, dim) * (ubounds - lbounds) + lbounds
        # Rescaling objective values to [0,1]
        objective_values = array([fun(x) for x in particles])
        objective_values = self.rescale(objective_values)
        # Datastructure containing all the population info
        self.pop_data = {
            p : {
                'x': particles[p],
                'obj': objective_values[p],
                'fitness': 0.0,
            } for p in range(self.alpha)
        }
        # Lazy compute max absolute value of pairwise epsilon indicator 
        self.indicator_max = max([abs(self.eps_indic_fun(i1, i2))
                                  for i1 in range(self.alpha)
                                  for i2 in range(self.alpha)
                                  if i1 != i2])
        # --- Initialize variables
        done = False
        generation = 0
        self.population_size = self.alpha
        self.free_indices = deque(range(self.alpha, self.alpha+2*self.n_offspring))

        while not done:
            # 2. Fitness assignment
            for i in self.pop_data.keys():
                self.compute_fitness(i)
            # 3 Environmental selection
            env_selection_ok = False
            while not env_selection_ok:
                # 3.1 Environmental selection
                fit_min = infty
                worst_fit = None
                for (k, v) in self.pop_data.items():
                    if v['fitness'] <= fit_min:
                        fit_min = v['fitness'] 
                        worst_fit = k

                # 3.3 Update fitness values
                for i in self.pop_data.keys():
                    self.pop_data[i]['fitness'] += exp(- self.eps_indic_fun(worst_fit, i) \
                                                       / (self.indicator_max * self.kappa))
                # 3.2 Remove individual
                self.population_size -= 1
                self.pop_data.pop(worst_fit)
                self.free_indices.append(worst_fit)
                # Continue while P does not exceed alpha
                env_selection_ok = self.population_size <= self.alpha

            # 4. Check convergence condition
            done = generation >= budget
            if done: break
            # 5. Mating selection
            # Perform binary tournament selection with replacement on P in order
            # to fill the temporary mating pool P'.
            item_keys = list(self.pop_data.keys())
            pool = []
            for i in range(2*self.n_offspring):
                p1, p2 = choice(item_keys, 2)
                if self.pop_data[p1]['fitness'] >= self.pop_data[p2]['fitness']:
                    pool.append(p1)
                else:
                    pool.append(p2)
            # 6. Variation
            for i in range(self.n_offspring):
                parent1 = self.pop_data[pool[i]]['x']
                parent2 = self.pop_data[pool[i+1]]['x']

                '''Application of recombination operators'''
                if binomial(1, self.pr_crossover):
                    child1, child2 = bounded_sbx(parent1, parent2, lbounds, ubounds)
                else:
                    child1 = parent1
                    child2 = parent2
                    
                if binomial(1, self.pr_mutation):
                    # Apply isotropic mutation operator
                    child1 += randn(dim) * self.noise_variance
                    child2 += randn(dim) * self.noise_variance

                ''' Adapt step-size - 1/5-th rule for (1+1)-ES: 
                self.compute_fitness(offspring)
                indicator = int(f_parent <= f_offspring)
                sigma *= power(exp(indicator - 0.2), 1/dim_sqrt)
                '''
                self.add_offspring(child1, fun(child1))
                self.add_offspring(child2, fun(child2))
                
            generation += 1

        best_fitness = -infty
        best_fit = None
        for (item, data) in self.pop_data.items():
            if data['fitness'] >= best_fitness:
                best_fitness = data['fitness']
                best_fit = item

        return self.pop_data[best_fit]['x']


    def add_offspring(self, offspring, objective_value):
        # Add the resulting offspring to P                
        self.population_size += 1
        indx = self.free_indices.pop()
        self.pop_data[indx] = {
            'x' : offspring,
            'obj': self.rescale_one(objective_value),
            'fitness': 0.0
        }
        
    def compute_fitness(self, particle):
        ''' For all vectors in P\{particle}, compute pairwise indicator function
        and sum to get fitness value.'''
        neg_sum = 0.0
        for indx in self.pop_data.keys():
            if indx != particle:
                neg_sum -= exp(-self.eps_indic_fun(indx, particle)\
                                  /(self.indicator_max * self.kappa))

        self.pop_data[particle]['fitness'] = neg_sum

    def eps_indic_fun(self, i1, i2):
        ''' Smallest epsilon such that f(x1) - \eps * f(x2) < 0'''
        obj1 = self.pop_data[i1]['obj']
        obj2 = self.pop_data[i2]['obj']
        diff = obj1 - obj2
        eps = diff.min()

        assert -1 <= eps <= 1, \
            'Bounds not respected: O1 = {}, O2 = {}, eps = {}'\
            .format(obj1, obj2, eps)

        return eps

    def rescale(self, objective):
        # Save objective lower and upper bounds
        self._min = objective.min(axis=0)
        self._max = objective.max(axis=0)

        # Column-wise rescaling 
        _, ndims = objective.shape
        for dim in range(ndims):
            objective[:, dim] = (objective[:, dim] - self._min[dim]) \
                      / (self._max[dim] - self._min[dim])
        return objective

    def rescale_one(self, objective):
        # Update objective lower and upper bounds
        self._min = minimum(self._min, objective)
        self._max = maximum(self._max, objective)
        # Rescale vector
        for dim in range(objective.shape[0]):
            objective[dim] = (objective[dim] - self._min[dim]) \
                   / (self._max[dim] - self._min[dim])
        return objective

if __name__ == '__main__':
    """call `experiment.main()`"""
    import experiment as cocoexp
    # main(budget, max_runs, current_batch, number_of_batches)
    cocoexp.main()
