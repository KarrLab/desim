"""
:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2017-03-26
:Copyright: 2016-2018, Karr Lab
:License: MIT
"""

import sys
import os
import unittest
import time
import tempfile
import shutil
import cProfile
import pstats
import copy
import random
import warnings

from de_sim.errors import SimulatorError
from de_sim.simulation_message import SimulationMessage
from de_sim.simulation_object import SimulationObject, ApplicationSimulationObject
from de_sim.template_sim_objs import TemplatePeriodicSimulationObject
from de_sim.simulation_engine import SimulationEngine
from tests.some_message_types import InitMsg, Eg1
from de_sim.shared_state_interface import SharedStateInterface
from wc_utils.util.misc import most_qual_cls_name
from wc_utils.util.dict import DictUtil
from de_sim.config.debug_logs import logs, config


ALL_MESSAGE_TYPES = [InitMsg, Eg1]


class BasicExampleSimulationObject(ApplicationSimulationObject):

    def __init__(self, name):
        SimulationObject.__init__(self, name)
        self.num = 0

    def send_initial_events(self):
        self.send_event(1, self, InitMsg())

    def get_state(self):
        return "self.num: {}".format(self.num)

    def handle_event(self, event): pass

    event_handlers = [(InitMsg, handle_event)]

    # register the message types sent
    messages_sent = ALL_MESSAGE_TYPES


class ExampleSimulationObject(BasicExampleSimulationObject):

    def handle_event(self, event):
        self.send_event(2.0, self, InitMsg())

    event_handlers = [(sim_msg_type, 'handle_event') for sim_msg_type in ALL_MESSAGE_TYPES]

    messages_sent = ALL_MESSAGE_TYPES


class InteractingSimulationObject(BasicExampleSimulationObject):

    def handle_event(self, event):
        self.num += 1
        # send an event to each object in the simulator
        for obj in self.simulator.simulation_objects.values():
            self.send_event(1, obj, InitMsg())

    event_handlers = [(sim_msg_type, 'handle_event') for sim_msg_type in ALL_MESSAGE_TYPES]

    messages_sent = ALL_MESSAGE_TYPES


class CyclicalMessagesSimulationObject(ApplicationSimulationObject):
    """ Send events around a cycle of objects
    """

    def __init__(self, name, obj_num, cycle_size, test_case):
        SimulationObject.__init__(self, name)
        self.obj_num = obj_num
        self.cycle_size = cycle_size
        self.test_case = test_case
        self.num_msgs = 0

    def next_obj(self):
        next = (self.obj_num+1) % self.cycle_size
        return self.simulator.simulation_objects[obj_name(next)]

    def send_initial_events(self):
        # send event to next CyclicalMessagesSimulationObject
        self.send_event(1, self.next_obj(), InitMsg())

    def handle_event(self, event):
        self.num_msgs += 1
        self.test_case.assertEqual(self.time, float(self.num_msgs))
        # send event to next CyclicalMessagesSimulationObject
        self.send_event(1, self.next_obj(), InitMsg())

    def get_state(self):
        return "self: obj_num: {} num_msgs: {}".format(self.obj_num, self.num_msgs)

    event_handlers = [(sim_msg_type, 'handle_event') for sim_msg_type in ALL_MESSAGE_TYPES]

    # register the message types sent
    messages_sent = ALL_MESSAGE_TYPES


class PeriodicSimulationObject(TemplatePeriodicSimulationObject):
    """ Self-clocking ApplicationSimulationObject

    Attributes:
        period (:obj:`float`): interval between events, in simulated seconds
    """

    def __init__(self, name, period):
        super().__init__(name, period)

    def handle_event(self):
        """ Handle the periodic event
        """
        return


NAME_PREFIX = 'sim_obj'

def obj_name(i):
    return '{}_{}'.format(NAME_PREFIX, i)


class TestSimulationEngine(unittest.TestCase):

    def setUp(self):
        # create simulator
        self.simulator = SimulationEngine()
        self.out_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.out_dir)

    def test_one_object_simulation(self):
        for operation in ['simulate', 'run']:
            obj = ExampleSimulationObject(obj_name(1))
            self.simulator.reset()
            self.simulator.add_object(obj)
            self.assertEqual(self.simulator.get_object(obj.name), obj)
            self.simulator.initialize()
            self.assertEqual(eval('self.simulator.'+operation+'(5.0)'), 3)

    def test_one_object_simulation_neg_endtime(self):
        obj = ExampleSimulationObject(obj_name(1))
        self.simulator.add_object(obj)
        self.simulator.initialize()
        self.assertEqual(self.simulator.simulate(-1), 0)

    def test_simulation_engine_exceptions(self):
        obj = ExampleSimulationObject(obj_name(1))
        with self.assertRaises(SimulatorError) as context:
            self.simulator.delete_object(obj)
        self.assertIn("cannot delete simulation object '{}'".format(obj.name), str(context.exception))

        no_such_obj_name = 'no such object'
        with self.assertRaises(SimulatorError) as context:
            self.simulator.get_object(no_such_obj_name)
        self.assertIn("cannot get simulation object '{}'".format(no_such_obj_name), str(context.exception))

        with self.assertRaises(SimulatorError) as context:
            self.simulator.simulate(5.0)
        self.assertIn('Simulation has not been initialized', str(context.exception))

        self.simulator.initialize()
        with self.assertRaises(SimulatorError) as context:
            self.simulator.simulate(5.0)
        self.assertIn('Simulation has no objects', str(context.exception))

        self.simulator.add_object(obj)
        with self.assertRaises(SimulatorError) as context:
            self.simulator.simulate(5.0)
        self.assertIn('Simulation has no events', str(context.exception))

        with self.assertRaises(SimulatorError) as context:
            self.simulator.add_object(obj)
        self.assertIn("cannot add simulation object '{}'".format(obj.name), str(context.exception))

        self.simulator.delete_object(obj)
        try:
            self.simulator.add_object(obj)
        except:
            self.fail('should be able to add object after delete')

        self.simulator.reset()
        self.simulator.initialize()
        self.simulator.add_object(obj)
        event_queue = self.simulator.event_queue
        event_queue.schedule_event(-1, -1, obj, obj, InitMsg())
        with self.assertRaises(AssertionError) as context:
            self.simulator.simulate(5.0)
        self.assertIn('object time', str(context.exception))
        self.assertIn('<= event time', str(context.exception))

        with self.assertRaises(SimulatorError) as context:
            self.simulator.initialize()
        self.assertEqual('Simulation has already been initialized', str(context.exception))

        self.simulator.reset()
        self.simulator.add_object(obj)
        self.simulator.initialize()
        with self.assertRaises(SimulatorError) as context:
            self.simulator.simulate(5.0, epsilon=0)
        self.assertRegex(str(context.exception), "epsilon (.*) plus end time (.*) must exceed end time")

    def test_simulation_end(self):
        # TODO(Arthur): make this a test or discard it
        self.simulator.add_object(BasicExampleSimulationObject('name'))
        self.simulator.initialize()
        # log "No events remain"
        self.simulator.simulate(5.0)

    def test_simulation_stop_condition(self):
        simulator = SimulationEngine()
        # 1 event/sec:
        simulator.add_object(PeriodicSimulationObject('name', 1))
        simulator.initialize()
        end_time = 10
        # execute to time <= end_time, with 1st event at time = 1
        self.assertEqual(simulator.simulate(end_time), end_time)

        __stop_cond_end = 3
        def stop_cond_eg(time):
            return __stop_cond_end <= time
        simulator = SimulationEngine(stop_condition=stop_cond_eg)
        simulator.add_object(PeriodicSimulationObject('name', 1))
        simulator.initialize()
        self.assertEqual(simulator.simulate(end_time), __stop_cond_end)

        simulator = SimulationEngine()
        simulator.add_object(PeriodicSimulationObject('name', 1))
        simulator.initialize()
        self.assertEqual(simulator.simulate(end_time, stop_condition=stop_cond_eg), __stop_cond_end)
        # todo: test log of 'Terminate with stop condition satisfied'

        with self.assertRaisesRegex(SimulatorError, 'stop_condition is not a function'):
            SimulationEngine(stop_condition='hello')

    def test_multi_object_simulation_and_reset(self):
        for i in range(1, 4):
            obj = ExampleSimulationObject(obj_name(i))
            self.simulator.add_object(obj)
        self.simulator.initialize()
        self.assertEqual(self.simulator.simulate(5.0), 9)

        event_count_lines = self.simulator.provide_event_counts().split('\n')[1:]
        for idx, line in enumerate(event_count_lines):
            self.assertIn('3', line)
            self.assertIn('ExampleSimulationObject', line)
            self.assertIn(obj_name(idx+1), line)

        self.simulator.reset()
        self.assertEqual(len(self.simulator.simulation_objects), 0)

    def test_multi_interacting_object_simulation(self):
        sim_objects = [InteractingSimulationObject(obj_name(i)) for i in range(1, 3)]
        self.simulator.add_objects(sim_objects)
        self.simulator.initialize()
        self.assertEqual(self.simulator.simulate(2.5), 4)

    def make_cyclical_messaging_network_sim(self, num_objs):
        # make simulation with cyclical messaging network
        sim_objects = [CyclicalMessagesSimulationObject(obj_name(i), i, num_objs, self)
            for i in range(num_objs)]
        self.simulator.add_objects(sim_objects)

    def test_cyclical_messaging_network(self):
        # test event times at simulation objects; this test should succeed with any
        # natural number for num_objs and any non-negative value of sim_duration
        self.make_cyclical_messaging_network_sim(10)
        self.simulator.initialize()
        self.simulator.simulate(20)
        # todo: this method doesn't contain tests

    def test_message_queues(self):
        warnings.simplefilter("ignore")
        class InactiveSimulationObject(ApplicationSimulationObject):

            def __init__(self):
                SimulationObject.__init__(self, 'inactive')

            def send_initial_events(self): pass

            def get_state(self): pass

            event_handlers = []

            messages_sent = [InitMsg]

        self.make_cyclical_messaging_network_sim(4)
        self.simulator.add_object(InactiveSimulationObject())
        self.simulator.initialize()
        queues = self.simulator.message_queues()
        for sim_obj_name in self.simulator.simulation_objects:
            self.assertIn(sim_obj_name, queues)

    # test simulation performance code:
    def prep_simulation(self, num_sim_objs):
        self.simulator.reset()
        self.make_cyclical_messaging_network_sim(num_sim_objs)
        self.simulator.initialize()

    def suspend_logging(self):
        self.saved_config = copy.deepcopy(config)
        DictUtil.set_value(config, 'level', 'error')

    def restore_logging(self):
        global config
        config = self.saved_config

    def test_log_conf(self):
        console_level = config['debug_logs']['handlers']['debug.console']['level']
        self.suspend_logging()
        self.assertEqual(config['debug_logs']['handlers']['debug.console']['level'], 'error')
        self.restore_logging()
        self.assertEqual(config['debug_logs']['handlers']['debug.console']['level'], console_level)

    @unittest.skip("performance scaling test; runs slowly")
    def test_performance(self):
        end_sim_time = 100
        max_num_sim_objs = 2000
        num_sim_objs = 4
        print()
        print("Performance test of cyclical messaging network: end simulation time: {}".format(end_sim_time))
        unprofiled_perf = ["\n#sim obs\t# events\trun time (s)\tevents/s".format()]

        self.suspend_logging()
        while num_sim_objs < max_num_sim_objs:

            # measure execution time
            self.prep_simulation(num_sim_objs)
            start_time = time.process_time()
            num_events = self.simulator.simulate(end_sim_time)
            run_time = time.process_time() - start_time
            self.assertEqual(num_sim_objs*end_sim_time, num_events)
            unprofiled_perf.append("{}\t{}\t{:8.3f}\t{:8.3f}".format(num_sim_objs, num_events,
                run_time, num_events/run_time))

            # profile
            self.prep_simulation(num_sim_objs)
            out_file = os.path.join(self.out_dir, "profile_out_{}.out".format(num_sim_objs))
            locals = {'self':self,
                'end_sim_time':end_sim_time}
            cProfile.runctx('num_events = self.simulator.simulate(end_sim_time)', {}, locals, filename=out_file)
            profile = pstats.Stats(out_file)
            print("Profile for {} simulation objects:".format(num_sim_objs))
            profile.strip_dirs().sort_stats('cumulative').print_stats(15)

            num_sim_objs *= 4

        print('Performance summary')
        print("\n".join(unprofiled_perf))
        self.restore_logging()


class Delicate(SimulationMessage):
    'Simulation message type for testing arrival order'
    attributes = ['sender_obj_num']


class ReproducibleTestSimulationObject(ApplicationSimulationObject):
    """ This sim obj is used to test whether the simulation engine is reproducible
    """
    def __init__(self, name, obj_num, array_size):
        SimulationObject.__init__(self, name)
        self.obj_num = obj_num
        self.array_size = array_size
        self.last_time = 0
        # Delicate messages should arrive before Hello messages; count the failures
        self.delicates_before_hello = 0
        # Delicate messages should be delivered in increasing (time, obj_num) order; count the failures
        self.disordered_delicates = 0
        self.last_time_delicate_num_pair = (0, 0)

    def next_objs(self, num_objs):
        # get the next num_objs sim objs in the array
        sim_objs = []
        for obj_num in range(self.obj_num, min(self.obj_num+num_objs, self.array_size)):
            sim_objs.append(self.simulator.get_object(obj_name(obj_num)))
        return sim_objs

    def sched_events(self):
        # send InitMsg to self in 1 and Delicate(id) to self and next obj in 1, but randomize send order
        receivers_n_messages = [(self, InitMsg())]
        for sim_obj in self.next_objs(2):
            receivers_n_messages.append((sim_obj, Delicate(self.obj_num)))
        random.shuffle(receivers_n_messages)
        for receiver,message in receivers_n_messages:
            self.send_event(1, receiver, message)

    def send_initial_events(self):
        self.sched_events()

    def handle_init_msg(self, event):
        self.last_time = self.time
        self.sched_events()

    def handle_delicate_msg(self, event):
        if self.last_time < self.time:
            self.delicates_before_hello +=1
        delicate_msg = event.message
        time_delicate_num_pair = (event.event_time, delicate_msg.sender_obj_num)
        if time_delicate_num_pair <= self.last_time_delicate_num_pair:
            self.disordered_delicates += 1
        self.last_time_delicate_num_pair = time_delicate_num_pair

    # register event_handler(s) in message priority order
    event_handlers = [(InitMsg, handle_init_msg), (Delicate, handle_delicate_msg)]

    # register the message types sent
    messages_sent = [InitMsg, Delicate]


class TestSimulationReproducibility(unittest.TestCase):

    NUM_SIM_OBJS = 4
    def test_reproducibility(self):
        self.simulator = SimulationEngine()

        # comprehensive reproducibility test:
        # test whether the simulation engine deterministically delivers events to objects
        # run a simulation in which sim objects execute multiple concurrent events that contain
        # messages with different types, and messages that have the same type and different contents
        # test all types of event and message sorting
        num_sim_objs = TestSimulationReproducibility.NUM_SIM_OBJS
        for i in range(num_sim_objs):
            obj_num = i+1
            self.simulator.add_object(
                ReproducibleTestSimulationObject(obj_name(obj_num), obj_num, num_sim_objs))
        self.simulator.initialize()
        self.simulator.simulate(30)
        for sim_obj in self.simulator.get_objects():
            self.assertEqual(0, sim_obj.delicates_before_hello)
            self.assertEqual(0, sim_obj.disordered_delicates)


class ExampleSharedStateObject(SharedStateInterface):

    def __init__(self, name, state):
        self.name = name
        self.state = state

    def get_name(self):
        return self.name

    def get_shared_state(self, time):
        return str(self.state)


class TestSimulationEngineLogging(unittest.TestCase):

    def setUp(self):
        self.example_shared_state_obj_name = 'example_shared_state_obj_name'
        self.example_shared_state_obj_state = [2, 'hi']
        self.example_shared_state_objs = \
            [ExampleSharedStateObject(self.example_shared_state_obj_name, self.example_shared_state_obj_state)]
        self.simulator = SimulationEngine(shared_state=self.example_shared_state_objs, debug_log=True)
        self.simulator.reset()

    # test logging with InteractingSimulationObject and a SharedStateInterface object
    def test_logging(self):
        num_sim_objs = 2
        sim_objects = [InteractingSimulationObject(obj_name(i+1)) for i in range(num_sim_objs)]
        self.simulator.add_objects(sim_objects)
        self.simulator.initialize()
        self.simulator.simulate(3)
        simulation_state = self.simulator.log_simulation_state()
        self.assertIn(self.example_shared_state_obj_name, simulation_state)
        self.assertIn(str(self.example_shared_state_obj_state), simulation_state)
        self.assertIn(InteractingSimulationObject.__name__, simulation_state)
        for sim_obj in sim_objects:
            self.assertIn(sim_obj.name, simulation_state)
        # message type name should be in event queue
        self.assertIn(InitMsg.__name__, simulation_state)
