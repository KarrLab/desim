""" Discrete event simulation engine

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2016-06-01
:Copyright: 2016-2018, Karr Lab
:License: MIT
"""

import datetime
import sys
from collections import Counter

from de_sim.config import core
from de_sim.discrete_event_sim_metadata import DiscreteEventSimMetadata, RunMetadata, AuthorMetadata
from de_sim.errors import SimulatorError
from de_sim.event import Event
from de_sim.shared_state_interface import SharedStateInterface
from de_sim.simulation_object import EventQueue, SimulationObject
from de_sim.utilities import SimulationProgressBar, FastLogger
from wc_utils.util.git import get_repo_metadata, RepoMetadataCollectionType


class SimulationEngine(object):
    """ A simulation engine

    General-purpose simulation mechanisms, including the simulation scheduler.
    Architected as an OO simulation that could be parallelized.

    `SimulationEngine` contains and manipulates global simulation data.
    SimulationEngine registers all simulation objects types and all simulation objects.
    Following `simulate()` it runs the simulation, scheduling objects to execute events
    in non-decreasing time order; and generates debugging output.

    Attributes:
        time (:obj:`float`): the simulations's current time
        simulation_objects (:obj:`dict` of `SimulationObject`): all simulation objects, keyed by name
        shared_state (:obj:`list` of :obj:`object`, optional): the shared state of the simulation, needed to
            log or checkpoint the entire state of a simulation; all objects in `shared_state` must
            implement `SharedStateInterface`
        debug_logs (:obj:`wc_utils.debug_logs.core.DebugLogsManager`): the debug logs
        fast_debug_file_logger (:obj:`FastLogger`): a fast logger for debugging messages
        fast_plotting_logger (:obj:`FastLogger`): a fast logger for trajectory data for plotting
        event_queue (:obj:`EventQueue`): the queue of future events
        progress (:obj:`SimulationProgressBar`): a real-time progress bar
        stop_condition (:obj:`function`, optional): if provided, a function that takes one argument:
            `time`; a simulation terminates if `stop_condition` returns `True`
        event_counts (:obj:`Counter`): a counter of event types
        metadata (:obj:`DiscreteEventSimMetadata`): metadata for a simulation run
        __initialized (:obj:`bool`): whether the simulation has been initialized

        Raises:
            :obj:`SimulatorError`: if the `stop_condition` is not callable
    """
    # Termination messages
    NO_EVENTS_REMAIN = " No events remain"
    END_TIME_EXCEEDED = " End time exceeded"
    TERMINATE_WITH_STOP_CONDITION_SATISFIED = " Terminate with stop condition satisfied"

    def __init__(self, shared_state=None, stop_condition=None):
        if shared_state is None:
            self.shared_state = []
        else:
            self.shared_state = shared_state
        self.debug_logs = core.get_debug_logs()
        self.fast_debug_file_logger = FastLogger(self.debug_logs.get_log('de_sim.debug.file'), 'debug')
        self.fast_plotting_logger = FastLogger(self.debug_logs.get_log('de_sim.plot.file'), 'debug')
        self.set_stop_condition(stop_condition)
        self.time = 0.0
        self.simulation_objects = {}
        self.log_with_time("SimulationEngine created")
        self.event_queue = EventQueue()
        self.event_counts = Counter()
        self.__initialized = False

    def set_stop_condition(self, stop_condition):
        """ Set the simulation engine's stop condition

        Attributes:
            stop_condition (:obj:`function`): a function that takes one argument
                `time`; `stop_condition` is executed and tested before each simulation event.
                If it returns `True` a simulation is terminated.

            Raises:
                :obj:`SimulatorError`: if the `stop_condition` is not callable
        """
        if stop_condition is not None and not callable(stop_condition):
            raise SimulatorError('stop_condition is not a function')
        self.stop_condition = stop_condition

    def add_object(self, simulation_object):
        """ Add a simulation object instance to this simulation

        Args:
            simulation_object (:obj:`SimulationObject`): a simulation object instance that
                will be used by this simulation

        Raises:
            :obj:`SimulatorError`: if the simulation object's name is already in use
        """
        name = simulation_object.name
        if name in self.simulation_objects:
            raise SimulatorError("cannot add simulation object '{}', name already in use".format(name))
        simulation_object.add(self)
        self.simulation_objects[name] = simulation_object

    def add_objects(self, simulation_objects):
        """ Add many simulation objects into the simulation

        Args:
            simulation_objects (:obj:`iterator` of `SimulationObject`): an iterator of simulation objects
        """
        for simulation_object in simulation_objects:
            self.add_object(simulation_object)

    def get_object(self, simulation_object_name):
        """ Get a simulation object instance

        Args:
            simulation_object_name (:obj:`str`): get a simulation object instance that is
                part of this simulation

        Raises:
            :obj:`SimulatorError`: if the simulation object is not part of this simulation
        """
        if simulation_object_name not in self.simulation_objects:
            raise SimulatorError("cannot get simulation object '{}'".format(simulation_object_name))
        return self.simulation_objects[simulation_object_name]

    def get_objects(self):
        """ Get all simulation object instances in the simulation
        """
        # TODO(Arthur): make this reproducible
        # TODO(Arthur): eliminate external calls to self.simulator.simulation_objects
        return self.simulation_objects.values()

    def delete_object(self, simulation_object):
        """ Delete a simulation object instance from this simulation

        Args:
            simulation_object (:obj:`SimulationObject`): a simulation object instance that is
                part of this simulation

        Raises:
            :obj:`SimulatorError`: if the simulation object is not part of this simulation
        """
        # TODO(Arthur): is this an operation that makes sense to support? if not, remove it; if yes,
        # remove all of this object's state from simulator, and test it properly
        name = simulation_object.name
        if name not in self.simulation_objects:
            raise SimulatorError("cannot delete simulation object '{}', has not been added".format(name))
        simulation_object.delete()
        del self.simulation_objects[name]

    def initialize(self):
        """ Initialize a simulation

        Call `send_initial_events()` in each simulation object that has been loaded.

        Raises:
            :obj:`SimulatorError`:  if the simulation has already been initialized
        """
        if self.__initialized:
            raise SimulatorError('Simulation has already been initialized')
        for sim_obj in self.simulation_objects.values():
            sim_obj.send_initial_events()
        self.event_counts.clear()
        self.__initialized = True

    '''
    problems
        AuthorMetadata needs data
        sim_config needs data
    '''
    def init_metadata_collection(self, sim_config=None):
        """ Initialize metatdata collection

        Call just before simulation starts, so that correct clock time of start is recorded

        Args:
            sim_config (:obj:`object`, optional): information about the simulation's configuration
                (e.g. start time, maximum time)
        """
        application, _ = get_repo_metadata(repo_type=RepoMetadataCollectionType.SCHEMA_REPO)
        author = AuthorMetadata()
        run = RunMetadata()
        run.record_ip_address()
        run.record_start()
        self.metadata = DiscreteEventSimMetadata(application, sim_config, run, author)

    def finish_metadata_collection(self, metadata_dir=None):
        """ Finish metatdata collection

        Args:
            metadata_dir (:obj:`str`, optional): directory for saving metadata; if not provided,
                then metatdata should be saved later
        """
        self.metadata.run.record_run_time()
        if metadata_dir:
            DiscreteEventSimMetadata.write_metadata(self.metadata, metadata_dir)

    def reset(self):
        """ Reset this `SimulationEngine`

        Set simulation time to 0, delete all objects, and reset any prior initialization.
        """
        self.time = 0.0
        for simulation_object in list(self.simulation_objects.values()):
            self.delete_object(simulation_object)
        self.event_queue.reset()
        self.__initialized = False

    def message_queues(self):
        """ Return a string listing all message queues in the simulation

        Returns:
            :obj:`str`: a list of all message queues in the simulation and their messages
        """
        data = ['Event queues at {:6.3f}'.format(self.time)]
        for sim_obj in sorted(self.simulation_objects.values(), key=lambda sim_obj: sim_obj.name):
            data.append(sim_obj.name + ':')
            rendered_eq = self.event_queue.render(sim_obj=sim_obj)
            if rendered_eq is None:
                data.append('Empty event queue')
            else:
                data.append(rendered_eq)
            data.append('')
        return '\n'.join(data)

    def run(self, time_max, **kwargs):
        """ Alias for simulate
        """
        return self.simulate(time_max, **kwargs)

    def simulate(self, time_max, stop_condition=None, progress=False, metadata_dir=None):
        """ Run the simulation

        Args:
            time_max (:obj:`float`): the time of the end of the simulation
            stop_condition (:obj:`function`, optional): if provided, a function that takes one argument
                `time`; a simulation terminates if the function returns `True`
            progress (:obj:`bool`, optional): if `True`, print a bar that dynamically reports the
                simulation's progress
            metadata_dir (:obj:`str`, optional): directory for saving metadata; if not provided,
                then metatdata should be saved later

        Returns:
            :obj:`int`: the number of times a simulation object executes `_handle_event()`. This may
                be smaller than the number of events sent, because simultaneous events at one
                simulation object are handled together.

        Raises:
            :obj:`SimulatorError`: if the simulation has not been initialized, or has no objects,
                or has no initial events
        """
        if not self.__initialized:
            raise SimulatorError("Simulation has not been initialized")

        if not len(self.get_objects()):
            raise SimulatorError("Simulation has no objects")

        if self.event_queue.empty():
            raise SimulatorError("Simulation has no events")

        # set up progress bar
        self.progress = SimulationProgressBar(progress)

        if stop_condition is not None:
            self.set_stop_condition(stop_condition)

        # write header to a plot log
        # plot logging is controlled by configuration files pointed to by config_constants and by env vars
        self.fast_plotting_logger.fast_log('# {:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()), sim_time=0)

        num_events_handled = 0
        self.log_with_time("Simulation to {} starting".format(time_max))

        try:
            self.progress.start(time_max)
            self.init_metadata_collection()
            # TODO(Arthur): perhaps 'while True':
            while self.time <= time_max:
                # use the stop condition

                if self.stop_condition is not None and self.stop_condition(self.time):
                    self.log_with_time(self.TERMINATE_WITH_STOP_CONDITION_SATISFIED)
                    self.progress.end()
                    break

                # get the earliest next event in the simulation
                # get parameters of next event from self.event_queue
                next_time = self.event_queue.next_event_time()
                next_sim_obj = self.event_queue.next_event_obj()

                if float('inf') == next_time:
                    self.log_with_time(self.NO_EVENTS_REMAIN)
                    self.progress.end()
                    break

                if time_max < next_time:
                    self.log_with_time(self.END_TIME_EXCEEDED)
                    self.progress.end()
                    break

                num_events_handled += 1

                self.time = next_time

                # error will only be raised if an init message sent to negative time or
                # an object decreases its time
                if next_time < next_sim_obj.time:
                    raise SimulatorError("Dispatching '{}', but event time ({}) "
                        "< object time ({})".format(next_sim_obj.name, next_time, next_sim_obj.time))

                # dispatch object that's ready to execute next event
                next_sim_obj.time = next_time

                self.log_with_time(" Running '{}' at {}".format(next_sim_obj.name, next_sim_obj.time))
                next_events = self.event_queue.next_events()
                for e in next_events:
                    e_name = ' - '.join([next_sim_obj.__class__.__name__, next_sim_obj.name, e.message.__class__.__name__])
                    self.event_counts[e_name] += 1
                next_sim_obj.__handle_event_list(next_events)
                self.progress.progress(next_time)

        except SimulatorError as e:
            raise SimulatorError('Simulation ended with error:\n' + str(e))

        self.finish_metadata_collection(metadata_dir=metadata_dir)
        return num_events_handled

    def log_with_time(self, msg):
        """Write a debug log message with the simulation time.
        """
        self.fast_debug_file_logger.fast_log(msg, sim_time=self.time)

    def provide_event_counts(self):
        """ Provide the simulation's categorized event counts

        Returns:
            :obj:`str`: the simulation's categorized event counts, in a tab-separated table
        """
        rv = ['\t'.join(['Count', 'Event type (Object type - object name - event type)'])]
        for event_type, count in self.event_counts.most_common():
            rv.append("{}\t{}".format(count, event_type))
        return '\n'.join(rv)

    def get_simulation_state(self):
        """ Get the simulation's state
        """
        # get simulation time
        state = [self.time]
        # get the state of all simulation object(s)
        sim_objects_state = []
        for simulation_object in self.simulation_objects.values():
            # get object name, type, current time, state
            state_entry = (simulation_object.__class__.__name__,
                simulation_object.name,
                simulation_object.time,
                simulation_object.get_state(),
                simulation_object.render_event_queue())
            sim_objects_state.append(state_entry)
        state.append(sim_objects_state)

        # get the shared state
        shared_objects_state = []
        for shared_state_obj in self.shared_state:
            state_entry = (shared_state_obj.__class__.__name__,
                shared_state_obj.get_name(),
                shared_state_obj.get_shared_state(self.time))
            shared_objects_state.append(state_entry)
        state.append(shared_objects_state)
        return state
