# -*- coding: utf-8 -*-
"""
@author: P.Vana
"""
import sys
import os
import numpy as np
import math
import time as tm

##################################################
# Neuron
##################################################
class Neuron:
    def __init__(self):
        # neuron position
        self.position = np.array((0, 0))
        # associated goal position
        self.goal_position = np.array((None, None))
        # index of the goal which inhibited this neuron
        self.goal_idx = None
        pass

    def adapt_neuron(self, beta, goal):
        self.position[0] += beta * (goal[0] - self.position[0])
        self.position[1] += beta * (goal[1] - self.position[1])
        pass
    
    def update_goal_position(self, goal, radius):
        # eps affects optimal solution
        eps = 0.0001
        dist = np.linalg.norm(self.position - goal)
        if dist < radius: #if inside the region, update normally
          self.goal_position = self.position
        else:
          self.goal_position = goal + (self.position - goal)*((radius - eps)/dist)

        return self.goal_position
        

##################################################
# SOM_solver: The main solver
# https://www.sciencedirect.com/science/article/pii/S0925231218306647#bib0053
##################################################
class SOM_solver:
    def __init__(self, goals, radius):
        self.goals = goals # vector containint coordinates of N goal cities
        self.radius = radius # size of the goal neighborhoods
        
        self.N = len(goals) # number of goals
        self.M = int(2.5 * self.N) # number of neurons
        
        # set the learning rate based on the neuron count N (original version)
        self.sigma = 12.41 * self.N + 0.6
        # faster version -- used only for UIR
        self.sigma = self.N
        self.mi = 0.5 # learning rate 
        self.alpha = 0.1 # gain decreasing rate
        # compute center and deviations of the goals
        np_goals = np.array([np.array(g) for g in goals])
        center = np.average(np_goals, axis=0)
        dev = np.std(np_goals, axis=0)
        
        # prepare matrix of the M neurons
        self.neurons = [Neuron() for i in range(0, self.M)]
        # initialize neurons by an ellipse
        for i in range(0, self.M):
            angle = (2 * math.pi * i) / self.M 
            direction = np.multiply([math.cos(angle), math.sin(angle)], dev)
            pos = center + direction
            self.neurons[i].position = pos

        pass    

    def select_winner(self, goal_idx):
        act_goal = self.goals[goal_idx]

        best_idx = None
        best_distance = sys.maxsize
        
        idx = 0
        for n in self.neurons:
            distance = np.linalg.norm(n.position - act_goal)
            if n.goal_idx == None and distance < best_distance:
                best_idx = idx
                best_distance = distance
            idx = idx + 1
    
        self.neurons[best_idx].goal_idx = goal_idx      
        return best_idx

    def neighborhood_fce(self, distance):
        return math.exp(-distance * distance / self.sigma / self.sigma)

    def learn_epoch(self, learning_epoch):
        # 1. clear values from the previous learning_epoch
        for n in self.neurons:
            n.goal_idx = self.gx = self.gy = None

        # chooce random order of the goals
        order = np.random.permutation(len(self.goals))

        # 2. precompute betas for faster computation
        distances = range(int(-0.2*self.M)+1, int(0.2*self.M))
        betas = [self.mi*self.neighborhood_fce(dst) for dst in distances]

        # 4. choose the closest neuron for each goal
        for goal_idx in order:
            act_goal = self.goals[goal_idx]
            winner_idx = self.select_winner(goal_idx)
            winner = self.neurons[winner_idx]
            alternate_goal = winner.update_goal_position(act_goal, self.radius)

            # neighbourhoods are given by the cardinal distances
            for i in range(len(distances)):
                d = distances[i]
                neighbour_idx = np.mod(winner_idx + d, len(self.neurons))
                self.neurons[neighbour_idx].adapt_neuron(betas[i], alternate_goal)

            act_beta = 0.1
            winner.adapt_neuron(act_beta, alternate_goal)
        # 5. update learing parameters
        self.sigma = (1 - self.alpha) * self.sigma  

    def reconstruct_path(self):
        inhibited_neurons = self.get_inhibited_neurons()
        path = [n.goal_position for n in inhibited_neurons]
        if len(path) > 0: 
            path = path + [path[0]]
        return path

    # save the best solution, print stats and return current error
    def statistics(self, iteration):
        error_sq = 0
        for n in filter(lambda x : x.goal_idx != None, self.neurons):
            dx = n.position[0] - n.goal_position[0]
            dy = n.position[1] - n.goal_position[1]
            dst_sq = dx*dx + dy*dy
            error_sq = max(error_sq, dst_sq)
        error = math.sqrt(error_sq)

        print('iteration {}: max_error = {}, time = {} s'.format(iteration, error, tm.clock()))
        return error

    def get_neurons_path(self):
        path = [n.position for n in self.neurons]
        if len(path) > 0: 
            path = path + [path[0]]
        return path

    def get_inhibited_neurons(self):
        return [x for x in self.neurons if x.goal_idx != None]
    