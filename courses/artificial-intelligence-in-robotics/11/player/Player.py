#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
from collections import defaultdict

import GridMap as gmap
import GridPlanner as gplanner

from pathlib import Path

import time
import random

import pickle

PURSUER = 1
EVADER = 2

GREEDY = "GREEDY"
MONTE_CARLO = "MONTE_CARLO"
VALUE_ITERATION = "VALUE_ITERATION"

class Player:
    def __init__(self, robots, role, policy=GREEDY, color='r', timeout=1.0, game=None):
        """
        Parameters
        ----------
        robots: list((in,int))
            coordinates of individual player's robots
        role: int
            player's role in the game
        """
        #list of the player's robots
        self.robots = robots[:]
        #next position of the player's robots
        self.next_robots = robots[:]

        if role == "EVADER":
            self.role = EVADER
        elif role == "PURSUER":
            self.role = PURSUER
        else:
            raise ValueError('Unknown player role')

        #selection of the policy
        if policy == GREEDY:
            self.policy = self.greedy_policy
        elif policy == MONTE_CARLO:
            self.policy = self.monte_carlo_policy
        elif policy == VALUE_ITERATION:
            self.policy = self.value_iteration_policy
        else:
            raise ValueError('Unknown policy')

        self.color = color #color for plotting purposes
        self.timeout = timeout #planning timeout fo MCTS
        self.game_name = game #game name for loading value iteration policies
        self.distances = None

        #values for the value iteration policy
        self.values = None

        #instantiation of helper planner
        self.Planner = gplanner.GridPlanner()
    
    #####################################################
    # Game interface functions
    #####################################################
    def add_robot(self, pos):
        """
        method to add a robot to the player
        
        Parameters
        ----------
        pos: (int,int)
            position of the robot
        """
        self.robots.append(pos)
        self.next_robots.append(pos)
    
    def del_robot(self, pos):
        """
        method to remove the player's robot 

        Parameters
        ----------
        pos: (int,int)
            position of the robot to be removed
        """
        idx = self.robots.index(pos)
        self.robots.pop(idx)
        self.next_robots.pop(idx)
    
    def calculate_step(self, gridmap, evaders, pursuers):
        """
        method to calculate the player's next step using selected policy
        
        Parameters
        ----------
        gridmap: GridMap
            map of the environment
        evaders: list((int,int))
            list of coordinates of evaders in the game (except the player's robots, if he is evader)
        pursuers: list((int,int))
            list of coordinates of pursuers in the game (except the player's robots, if he is pursuer)
        """
        self.policy(gridmap, evaders, pursuers)
    
    def take_step(self):
        """
        method to perform the step 
        """
        self.robots = self.next_robots[:]

    #####################################################
    #####################################################
    # FLOYD WARSHALL
    #####################################################
    #####################################################
    def get_array_of_coordinates(self, n, m):
        coords = []
        for i in range(n):
            for j in range(m):
                coords.append((i, j))
        return coords

    def prepare_weight_matrix(self, gridmap):
        coords = list(filter(lambda coord: gridmap.passable(coord), self.get_array_of_coordinates(gridmap.width, gridmap.height)))
        w = defaultdict(dict)
        for coord1 in coords:
            for coord2 in coords:
                if gridmap.passable(coord1) and gridmap.passable(coord2):
                    w[coord1][coord2] = self.dist(gridmap, coord1, coord2)
        return w

    def floyd_warshall(self, gridmap, w):
        coords = list(filter(lambda coord: gridmap.passable(coord), self.get_array_of_coordinates(gridmap.width, gridmap.height)))
        dist, path = defaultdict(dict), defaultdict(dict)
        for coord1 in coords:
            for coord2 in coords:
                dist[coord1][coord1] = 0
                dist[coord2][coord2] = 0
                dist[coord1][coord2] = np.inf
                if coord1 in w and coord2 in w[coord1]:
                    dist[coord1][coord2] = w[coord1][coord2]
                    path[coord1][coord2] = [coord1, coord2]

        for k in coords:
            for i in coords:
                for j in coords:
                    if dist[i][j] > dist[i][k] + dist[k][j]:
                        dist[i][j] = dist[i][k] + dist[k][j]
                        path[i][j] = path[i][k] + path[k][j]

        return dist, path

    def select_closest_to_closest_evader(self, neighbors, evaders, distances):
        best = np.inf
        best_neighbor = None
        for n in neighbors:
            for e in evaders:
                if distances[n][e] < best:
                    best = distances[n][e]
                    best_neighbor = n

        return best_neighbor

    def select_most_distant_to_pursuers(self, neighbors, pursuers, distances):
        best = -1
        best_neighbor = None
        for n in neighbors:
            d = np.inf
            for p in pursuers:
                d = min(d, distances[n][p])
            if d > best:
                best = d
                best_neighbor = n

        return best_neighbor
        
    #####################################################
    #####################################################
    # GREEDY POLICY
    #####################################################
    #####################################################
    def greedy_policy(self, gridmap, evaders, pursuers, epsilon=1):
        """
        Method to calculate the greedy policy action
        
        Parameters
        ----------
        gridmap: GridMap
            Map of the environment
        evaders: list((int,int))
            list of coordinates of evaders in the game (except the player's robots, if he is evader)
        pursuers: list((int,int))
            list of coordinates of pursuers in the game (except the player's robots, if he is pursuer)
        epsilon: float (optional)
            optional epsilon-greedy parameter
        """
        self.next_robots = self.robots[:]
        if self.distances is None:
            w = self.prepare_weight_matrix(gridmap)
            self.distances, _ = self.floyd_warshall(gridmap, w)

        #for each of player's robots plan their actions
        for idx in range(0, len(self.robots)):
            robot = self.robots[idx]
            neighbors = gridmap.neighbors4(robot)

            if random.random() < epsilon:
                #select the next action based on own role
                if self.role == PURSUER:
                    self.next_robots[idx] = self.select_closest_to_closest_evader(neighbors, evaders, self.distances)
                elif self.role == EVADER:
                    self.next_robots[idx] = self.select_most_distant_to_pursuers(neighbors, pursuers, self.distances)
            else:
                ##################################################
                # RANDOM Policy
                ##################################################
                #introducing randomness in neighbor selection
                random.shuffle(neighbors)
                #select random goal
                pos_selected = neighbors[0]
                self.next_robots[idx] = pos_selected
                ##################################################
    
    #####################################################
    #####################################################
    # MONTE CARLO TREE SEARCH POLICY
    #####################################################
    #####################################################
    def monte_carlo_policy(self, gridmap, evaders, pursuers):
        """
        Method to calculate the monte carlo tree search policy action
        
        Parameters
        ----------
        gridmap: GridMap
            Map of the environment
        evaders: list((int,int))
            list of coordinates of evaders in the game (except the player's robots, if he is evader)
        pursuers: list((int,int))
            list of coordinates of pursuers in the game (except the player's robots, if he is pursuer)
        """
        self.next_robots = self.robots[:]
        
        #for each of player's robots plan their actions
        for idx in range(0, len(self.robots)):
            robot = self.robots[idx]
            
            #measure the time for selecting next action
            clk = time.time()

            while (time.time() - clk) < self.timeout:
                #TODO: implement MCTS policy

                ##################################################
                # RANDOM Policy
                ##################################################
                #extract possible coordinates to go (actions)
                neighbors = gridmap.neighbors4(robot)
                #introducing randomness in neighbor selection
                random.shuffle(neighbors)
                
                #select random goal
                pos_selected = neighbors[0]
                ##################################################

            #select the next action
            self.next_robots[idx] = pos_selected


    #####################################################
    #####################################################
    # VALUE ITERATION POLICY
    #####################################################
    #####################################################
    def value_iteration_policy(self, gridmap, evaders, pursuers):
        """
        Method to calculate the value-iteration policy action
        
        Parameters
        ----------
        gridmap: GridMap
            Map of the environment
        evaders: list((int,int))
            list of coordinates of evaders in the game (except the player's robots, if he is evader)
        pursuers: list((int,int))
            list of coordinates of pursuers in the game (except the player's robots, if he is pursuer)
        """
        self.next_robots = self.robots[:]

        #if there are not precalculated values for policy
        if not self.values: 
            policy_file = Path("policies/" + self.game_name + ".policy")
            ################################################### 
            #if there is policy file, load it...
            ################################################### 
            if policy_file.is_file():
                #load the strategy file
                self.values = pickle.load(open(policy_file, 'rb')) 

            ################################################### 
            #...else calculate the policy
            ################################################### 
            else:
                #TODO:calculate the Value iteration policy
                self.values = None

                #save the policy
                pickle.dump([self.values],open(policy_file,'wb'))
        


        for idx in range(0, len(self.robots)):
            robot = self.robots[idx]
            
            #############################################
            # TODO: decide the next action  based on the policy
            #############################################
            neighbors = gridmap.neighbors4(robot)
            #introducing randomness in neighbor selection
            random.shuffle(neighbors)
            
            #select random goal
            pos_selected = neighbors[0]
            #############################################

            #select the next action for the robots
            self.next_robots[idx] = pos_selected
            
    
    #####################################################
    # Helper functions
    #####################################################
    def dist(self, gridmap, coord1, coord2):
        #using A* to get shortest path
        pth = self.Planner.plan(gridmap, coord1, coord2, neigh='N4')
        dst = len(pth)
        return dst

