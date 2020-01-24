import sys
import json
import logging
import time
import random
from .view import View
from .screenshot import Screenshot
from .abstract_state import AbstractState
from abc import abstractmethod
from .view import View


from .input_event import InputEvent, KeyEvent, IntentEvent, TouchEvent, ManualEvent, SetTextEvent, DoubleRotationEvent, \
    FillUIEvent, ScrollEvent, LongTouchEvent
from .utg import UTG

# !!! DataLoss policy parameters !!!
# Max threshold for Screenshot comparison
MAX_THRESHOLD_FOR_SCREENSHOT_COMPARISON = 0.15
DEFAULT_EPSILON = 0.1

# Max number of restarts
MAX_NUM_RESTARTS = 5
# Max number of steps outside the app
MAX_NUM_STEPS_OUTSIDE = 5
MAX_NUM_STEPS_OUTSIDE_KILL = 10
# Max number of replay tries
MAX_REPLY_TRIES = 5
# Default orientation = 0 degrees
DEFAULT_ORIENTATION = 0

# Some input event flags
EVENT_FLAG_STARTED = "+started"
EVENT_FLAG_START_APP = "+start_app"
EVENT_FLAG_STOP_APP = "+stop_app"
EVENT_FLAG_EXPLORE = "+explore"
EVENT_FLAG_NAVIGATE = "+navigate"
EVENT_FLAG_TOUCH = "+touch"

# Policy taxanomy
POLICY_NAIVE_DFS = "dfs_naive"
POLICY_GREEDY_DFS = "dfs_greedy"
POLICY_NAIVE_BFS = "bfs_naive"
POLICY_GREEDY_BFS = "bfs_greedy"
POLICY_REPLAY = "replay"
POLICY_MANUAL = "manual"
POLICY_MONKEY = "monkey"
POLICY_NONE = "none"
POLICY_DATA_LOSS = "data_loss"


class InputInterruptedException(Exception):
    pass


class DataLossException(Exception):
    pass


class InputPolicy(object):
    """
    This class is responsible for generating events to stimulate more app behaviour
    It should call AppEventManager.send_event method continuously
    """

    def __init__(self, device, app):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.device = device
        self.app = app
        self.master = None

    def start(self, input_manager):
        """
        start producing events
        :param input_manager: instance of InputManager
        """
        count = 0

        if isinstance(self, DataLossPolicy) and self.device.output_dir is not None:
            start_time = time.strftime("%Y-%m-%d %H-%M-%S")
            DataLossPolicy.create_html_report_head(self.report_file_name)

        while input_manager.enabled and count < input_manager.event_count:
            try:
                # make sure the first event is go to HOME screen
                # the second event is to start the app
                # the third event is to set default orientation
                if count == 0 and self.master is None:
                    # first of all, enable the screen rotation
                    self.device.enable_rotation()
                    event = KeyEvent(name="HOME")
                elif count == 1 and self.master is None:
                    event = IntentEvent(self.app.get_start_intent())
                elif count == 2 and self.master is None and self.device.adb.get_orientation() != 0:
                    self.device.set_orientation(DEFAULT_ORIENTATION)
                    time.sleep(5)
                    continue
                else:
                    event = self.generate_event()

                if isinstance(self, DataLossPolicy) and isinstance(event, DoubleRotationEvent):
                    screenshot_before = Screenshot(img=self.device.take_screenshot_using_adb())
                    self.double_rotation_num += 1

                input_manager.add_event(event)
                if isinstance(event, IntentEvent):
                    time.sleep(5)

                if isinstance(self, DataLossPolicy) and isinstance(event, DoubleRotationEvent):
                    screenshot_after = Screenshot(img=self.device.take_screenshot_using_adb())

                if isinstance(self, DataLossPolicy):
                    self.current_state = self.device.get_current_state()
                    data_time = time.strftime("%Y-%m-%d %H-%M-%S")
                    if isinstance(event, DoubleRotationEvent):
                        self.check_data_loss(event, screen_before=screenshot_before, screen_after=screenshot_after)
                    if count >= 1 and self.report_file_name is not None:
                        self.report(event=event, data_time=data_time)

            except KeyboardInterrupt:
                break
            except DataLossException as ex:
                print(ex.message)
                self.data_loss_num += 1
                data_loss_desc = ex.message[ex.message.index(".") + 2:len(ex.message) - 1]
                self.report(event=event, data_time=data_time, exception_str="DataLossException", exception_desc=data_loss_desc)
                self.save_data_loss_source(data_time=data_time, img_after=screenshot_after, img_before=screenshot_before)
            except InputInterruptedException as e:
                self.logger.warning("stop sending events: %s" % e)
                break
            except Exception as e:
                self.logger.warning("exception during sending events: %s" % e)
                import traceback
                traceback.print_exc()
                continue
            count += 1
            print("[INFO]   " + str(count) + " events have been generated")
        if isinstance(self, DataLossPolicy) and self.device.output_dir is not None:
            DataLossPolicy.create_html_report_tail(file_path=self.report_file_name, event_num=count, data_loss_num=self.data_loss_num,
                                                   fat_exc_num=self.fatal_exception_num, activity_test=self.activity_tested_coverage, dr_num=self.double_rotation_num,
                                                   fu_num=self.fillUI_num, activity_cov=self.activity_coverage, start_time=start_time,
                                                   end_time=str(time.strftime("%Y-%m-%d %H-%M-%S")))

    @abstractmethod
    def generate_event(self):
        """
        generate an event
        @return:
        """
        pass


class NoneInputPolicy(InputPolicy):
    """
    do not send any event
    """

    def __init__(self, device, app):
        super(NoneInputPolicy, self).__init__(device, app)

    def generate_event(self):
        """
        generate an event
        @return:
        """
        return None


class UtgBasedInputPolicy(InputPolicy):
    """
    state-based input policy
    """

    def __init__(self, device, app, random_input):
        super(UtgBasedInputPolicy, self).__init__(device, app)
        self.random_input = random_input
        self.script = None
        self.master = None
        self.script_events = []
        self.last_event = None
        self.last_state = None
        self.current_state = None
        self.utg = UTG(device=device, app=app, random_input=random_input)
        self.script_event_idx = 0
        self.index = 0
        self.__activity_initial_state_dict = {}
        if self.device.humanoid is not None:
            self.humanoid_view_trees = []
            self.humanoid_events = []

    def generate_event(self):
        """
        generate an event
        @return:
        """

        self.current_state = self.device.get_current_state()

        if self.current_state is None:
            import time
            time.sleep(5)
            return KeyEvent(name="BACK")

        self.__update_utg()

        # update last view trees for humanoid
        if self.device.humanoid is not None:
            self.humanoid_view_trees = self.humanoid_view_trees + [self.current_state.view_tree]
            if len(self.humanoid_view_trees) > 4:
                self.humanoid_view_trees = self.humanoid_view_trees[1:]

        event = None

        # if the previous operation is not finished, continue
        if len(self.script_events) > self.script_event_idx:
            event = self.script_events[self.script_event_idx].get_transformed_event(self)
            self.script_event_idx += 1

        # First try matching a state defined in the script
        if event is None and self.script is not None:
            operation = self.script.get_operation_based_on_state(self.current_state)
            if operation is not None:
                self.script_events = operation.events
                # restart script
                event = self.script_events[0].get_transformed_event(self)
                self.script_event_idx = 1

        if event is None:
            event = self.generate_event_based_on_utg()

        # update last events for humanoid
        if self.device.humanoid is not None:
            self.humanoid_events = self.humanoid_events + [event]
            if len(self.humanoid_events) > 3:
                self.humanoid_events = self.humanoid_events[1:]

        self.last_event = event
        self.last_state = self.current_state
        return event

    def __update_utg(self):
        self.utg.add_transition(self.last_event, self.last_state, self.current_state)

    @abstractmethod
    def generate_event_based_on_utg(self):
        """
        generate an event based on UTG
        :return: InputEvent
        """
        pass


class UtgNaiveSearchPolicy(UtgBasedInputPolicy):
    """
    depth-first strategy to explore UFG (old)
    """

    def __init__(self, device, app, random_input, search_method):
        super(UtgNaiveSearchPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.explored_views = set()
        self.state_transitions = set()
        self.search_method = search_method

        self.last_event_flag = ""
        self.last_event_str = None
        self.last_state = None

        self.preferred_buttons = ["yes", "ok", "activate", "detail", "more", "access",
                                  "allow", "check", "agree", "try", "go", "next"]

    def generate_event_based_on_utg(self):
        """
        generate an event based on current device state
        note: ensure these fields are properly maintained in each transaction:
          last_event_flag, last_touched_view, last_state, exploited_views, state_transitions
        @return: InputEvent
        """
        self.save_state_transition(self.last_event_str, self.last_state, self.current_state)

        if self.device.is_foreground(self.app):
            # the app is in foreground, clear last_event_flag
            self.last_event_flag = EVENT_FLAG_STARTED
        else:
            number_of_starts = self.last_event_flag.count(EVENT_FLAG_START_APP)
            # If we have tried too many times but the app is still not started, stop DroidBot
            if number_of_starts > MAX_NUM_RESTARTS:
                raise InputInterruptedException("The app cannot be started.")

            # if app is not started, try start it
            if self.last_event_flag.endswith(EVENT_FLAG_START_APP):
                # It seems the app stuck at some state, and cannot be started
                # just pass to let viewclient deal with this case
                self.logger.info("The app had been restarted %d times.", number_of_starts)
                self.logger.info("Trying to restart app...")
                pass
            else:
                start_app_intent = self.app.get_start_intent()

                self.last_event_flag += EVENT_FLAG_START_APP
                self.last_event_str = EVENT_FLAG_START_APP
                return IntentEvent(start_app_intent)

        # select a view to click
        view_to_touch = self.select_a_view(self.current_state)

        # if no view can be selected, restart the app
        if view_to_touch is None:
            stop_app_intent = self.app.get_stop_intent()
            self.last_event_flag += EVENT_FLAG_STOP_APP
            self.last_event_str = EVENT_FLAG_STOP_APP
            return IntentEvent(stop_app_intent)

        view_to_touch_str = view_to_touch['view_str']
        if view_to_touch_str.startswith('BACK'):
            result = KeyEvent('BACK')
        else:
            result = TouchEvent(view=view_to_touch)

        self.last_event_flag += EVENT_FLAG_TOUCH
        self.last_event_str = view_to_touch_str
        self.save_explored_view(self.current_state, self.last_event_str)
        return result

    def select_a_view(self, state):
        """
        select a view in the view list of given state, let droidbot touch it
        @param state: DeviceState
        @return:
        """
        views = []
        for view in state.views:
            if view['enabled'] and len(view['children']) == 0:
                views.append(view)

        if self.random_input:
            random.shuffle(views)

        # add a "BACK" view, consider go back first/last according to search policy
        mock_view_back = {'view_str': 'BACK_%s' % state.foreground_activity,
                          'text': 'BACK_%s' % state.foreground_activity}
        if self.search_method == POLICY_NAIVE_DFS:
            views.append(mock_view_back)
        elif self.search_method == POLICY_NAIVE_BFS:
            views.insert(0, mock_view_back)

        # first try to find a preferable view
        for view in views:
            view_text = view['text'] if view['text'] is not None else ''
            view_text = view_text.lower().strip()
            if view_text in self.preferred_buttons \
                    and (state.foreground_activity, view['view_str']) not in self.explored_views:
                self.logger.info("selected an preferred view: %s" % view['view_str'])
                return view

        # try to find a un-clicked view
        for view in views:
            if (state.foreground_activity, view['view_str']) not in self.explored_views:
                self.logger.info("selected an un-clicked view: %s" % view['view_str'])
                return view

        # if all enabled views have been clicked, try jump to another activity by clicking one of state transitions
        if self.random_input:
            random.shuffle(views)
        transition_views = {transition[0] for transition in self.state_transitions}
        for view in views:
            if view['view_str'] in transition_views:
                self.logger.info("selected a transition view: %s" % view['view_str'])
                return view

        # no window transition found, just return a random view
        # view = views[0]
        # self.logger.info("selected a random view: %s" % view['view_str'])
        # return view

        # DroidBot stuck on current state, return None
        self.logger.info("no view could be selected in state: %s" % state.tag)
        return None

    def save_state_transition(self, event_str, old_state, new_state):
        """
        save the state transition
        @param event_str: str, representing the event cause the transition
        @param old_state: DeviceState
        @param new_state: DeviceState
        @return:
        """
        if event_str is None or old_state is None or new_state is None:
            return
        if new_state.is_different_from(old_state):
            self.state_transitions.add((event_str, old_state.tag, new_state.tag))

    def save_explored_view(self, state, view_str):
        """
        save the explored view
        @param state: DeviceState, where the view located
        @param view_str: str, representing a view
        @return:
        """
        if not state:
            return
        state_activity = state.foreground_activity
        self.explored_views.add((state_activity, view_str))


class UtgGreedySearchPolicy(UtgBasedInputPolicy):
    """
    DFS/BFS (according to search_method) strategy to explore UFG (new)
    """

    def __init__(self, device, app, random_input, search_method):
        super(UtgGreedySearchPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.search_method = search_method

        self.preferred_buttons = ["yes", "ok", "activate", "detail", "more", "access",
                                  "allow", "check", "agree", "try", "go", "next"]

        self.__nav_target = None
        self.__nav_num_steps = -1
        self.__num_restarts = 0
        self.__num_steps_outside = 0
        self.__event_trace = ""
        self.__missed_states = set()
        self.__random_explore = False

    def generate_event_based_on_utg(self):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        current_state = self.current_state
        self.logger.info("Current state: %s" % current_state.state_str)
        # initially, __missed_states is an empty set()
        if current_state.state_str in self.__missed_states:
            self.__missed_states.remove(current_state.state_str)

        # the function get_app_activity_depth returns the depth (int) of the app in the activity stack
        # it returns 0 if the app is the first app in the activity stack
        # it returns a number > 0 which represents the position of the activity in the stack
        # it returns -1 if the activity isn't in the activity stack
        if current_state.get_app_activity_depth(self.app) < 0:
            # If the app is not in the activity stack
            start_app_intent = self.app.get_start_intent()

            # It seems the app stucks at some state, has been
            # 1) force stopped (START, STOP)
            #    just start the app again by increasing self.__num_restarts
            # 2) started at least once and cannot be started (START)
            #    pass to let viewclient deal with this case
            # 3) nothing
            #    a normal start. clear self.__num_restarts.

            if self.__event_trace.endswith(EVENT_FLAG_START_APP + EVENT_FLAG_STOP_APP) \
                    or self.__event_trace.endswith(EVENT_FLAG_START_APP):
                self.__num_restarts += 1
                self.logger.info("The app had been restarted %d times.", self.__num_restarts)
            else:
                self.__num_restarts = 0

            # pass (START) through
            if not self.__event_trace.endswith(EVENT_FLAG_START_APP):
                if self.__num_restarts > MAX_NUM_RESTARTS:
                    # If the app had been restarted too many times, enter random mode
                    msg = "The app had been restarted too many times. Entering random mode."
                    self.logger.info(msg)
                    self.__random_explore = True
                else:
                    # Start the app
                    self.__event_trace += EVENT_FLAG_START_APP
                    self.logger.info("Trying to start the app...")
                    return IntentEvent(intent=start_app_intent)

        elif current_state.get_app_activity_depth(self.app) > 0:
            # If the app is in activity stack but is not in foreground
            self.__num_steps_outside += 1

            if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE:
                # If the app has not been in foreground for too long, try to go back
                if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE_KILL:
                    stop_app_intent = self.app.get_stop_intent()
                    go_back_event = IntentEvent(stop_app_intent)
                else:
                    go_back_event = KeyEvent(name="BACK")
                self.__event_trace += EVENT_FLAG_NAVIGATE
                self.logger.info("Going back to the app...")
                return go_back_event
        else:
            # If the app is in foreground
            self.__num_steps_outside = 0

        # Get all possible input events
        possible_events = current_state.get_possible_input()

        if self.random_input:
            random.shuffle(possible_events)

        if self.search_method == POLICY_GREEDY_DFS:
            possible_events.append(KeyEvent(name="BACK"))
        elif self.search_method == POLICY_GREEDY_BFS:
            possible_events.insert(0, KeyEvent(name="BACK"))

        # get humanoid result, use the result to sort possible events
        # including back events
        if self.device.humanoid is not None:
            possible_events = self.__sort_inputs_by_humanoid(possible_events)

        # If there is an unexplored event, try the event first
        for input_event in possible_events:
            if not self.utg.is_event_explored(event=input_event, state=current_state):
                self.logger.info("Trying an unexplored event.")
                self.__event_trace += EVENT_FLAG_EXPLORE
                return input_event

        # If we are here, we haven't found unexplored events.

        target_state = self.__get_nav_target(current_state)
        if target_state:
            event_path = self.utg.get_event_path(current_state=current_state, target_state=target_state)
            if event_path and len(event_path) > 0:
                self.logger.info("Navigating to %s, %d steps left." % (target_state.state_str, len(event_path)))
                self.__event_trace += EVENT_FLAG_NAVIGATE
                return event_path[0]

        if self.__random_explore:
            self.logger.info("Trying random event.")
            random.shuffle(possible_events)
            return possible_events[0]

        # If couldn't find a exploration target, stop the app
        stop_app_intent = self.app.get_stop_intent()
        self.logger.info("Cannot find an exploration target. Trying to restart app...")
        self.__event_trace += EVENT_FLAG_STOP_APP
        return IntentEvent(intent=stop_app_intent)

    def __sort_inputs_by_humanoid(self, possible_events):
        if sys.version.startswith("3"):
            from xmlrpc.client import ServerProxy
        else:
            from xmlrpclib import ServerProxy
        proxy = ServerProxy("http://%s/" % self.device.humanoid)
        request_json = {
            "history_view_trees": self.humanoid_view_trees,
            "history_events": [x.__dict__ for x in self.humanoid_events],
            "possible_events": [x.__dict__ for x in possible_events],
            "screen_res": [self.device.display_info["width"],
                           self.device.display_info["height"]]
        }
        result = json.loads(proxy.predict(json.dumps(request_json)))
        new_idx = result["indices"]
        text = result["text"]
        new_events = []

        # get rid of infinite recursive by randomizing first event
        if not self.utg.is_state_reached(self.current_state):
            new_first = random.randint(0, len(new_idx) - 1)
            new_idx[0], new_idx[new_first] = new_idx[new_first], new_idx[0]

        for idx in new_idx:
            if isinstance(possible_events[idx], SetTextEvent):
                possible_events[idx].text = text
            new_events.append(possible_events[idx])
        return new_events

    def __get_nav_target(self, current_state):
        # If last event is a navigation event
        if self.__nav_target and self.__event_trace.endswith(EVENT_FLAG_NAVIGATE):
            event_path = self.utg.get_event_path(current_state=current_state, target_state=self.__nav_target)
            if event_path and 0 < len(event_path) <= self.__nav_num_steps:
                # If last navigation was successful, use current nav target
                self.__nav_num_steps = len(event_path)
                return self.__nav_target
            else:
                # If last navigation was failed, add nav target to missing states
                self.__missed_states.add(self.__nav_target.state_str)

        reachable_states = self.utg.get_reachable_states(current_state)
        if self.random_input:
            random.shuffle(reachable_states)

        for state in reachable_states:
            # Only consider foreground states
            if state.get_app_activity_depth(self.app) != 0:
                continue
            # Do not consider missed states
            if state.state_str in self.__missed_states:
                continue
            # Do not consider explored states
            if self.utg.is_state_explored(state):
                continue
            self.__nav_target = state
            event_path = self.utg.get_event_path(current_state=current_state, target_state=self.__nav_target)
            if len(event_path) > 0:
                self.__nav_num_steps = len(event_path)
                return state

        self.__nav_target = None
        self.__nav_num_steps = -1
        return None


class UtgReplayPolicy(InputPolicy):
    """
    Replay DroidBot output generated by UTG policy
    """

    def __init__(self, device, app, replay_output):
        super(UtgReplayPolicy, self).__init__(device, app)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.replay_output = replay_output

        import os
        event_dir = os.path.join(replay_output, "events")
        self.event_paths = sorted([os.path.join(event_dir, x) for x in
                                   next(os.walk(event_dir))[2]
                                   if x.endswith(".json")])
        # skip HOME and start app intent
        self.event_idx = 2
        self.num_replay_tries = 0
        print(self.event_paths)

    def generate_event(self):
        """
        generate an event based on replay_output
        @return: InputEvent
        """
        import time
        while self.event_idx < len(self.event_paths) and \
              self.num_replay_tries < MAX_REPLY_TRIES:
            self.num_replay_tries += 1
            current_state = self.device.get_current_state()
            if current_state is None:
                time.sleep(5)
                self.num_replay_tries = 0
                return KeyEvent(name="BACK")

            curr_event_idx = self.event_idx
            out_of_app = False
            while curr_event_idx < len(self.event_paths):
                if current_state.foreground_activity[current_state.foreground_activity.rfind('.') + 1:] == "GrantPermissionsActivity":
                    views = current_state.views
                    for view in views:
                        text = view["text"]
                        if text is not None and text.encode("ascii", "ignore").lower() in ["allow", "ok"]:
                            return TouchEvent(view=view)
                event_path = self.event_paths[curr_event_idx]
                with open(event_path, "r") as f:
                    curr_event_idx += 1

                    try:
                        event_dict = json.load(f)
                    except Exception as e:
                        self.logger.info("Loading %s failed" % event_path)
                        continue
                    self.logger.info("Replaying %s" % event_path)
                    self.event_idx = curr_event_idx
                    self.num_replay_tries = 0
                    return InputEvent.from_dict(event_dict["event"])

            time.sleep(5)

        raise InputInterruptedException("No more record can be replayed.")


class ManualPolicy(UtgBasedInputPolicy):
    """
    manually explore UFG
    """

    def __init__(self, device, app):
        super(ManualPolicy, self).__init__(device, app, False)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.__first_event = True

    def generate_event_based_on_utg(self):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        if self.__first_event:
            self.__first_event = False
            self.logger.info("Trying to start the app...")
            start_app_intent = self.app.get_start_intent()
            return IntentEvent(intent=start_app_intent)
        else:
            return ManualEvent()


class DataLossPolicy(InputPolicy):
    """
    Data loss policy
    """

    def __init__(self, device, app, epsilon, scroll_full_down_y):
        super(DataLossPolicy, self).__init__(device, app)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.preferred_buttons = ["allow", "ok"]
        self.__forbidden_views = ["layout"]
        self.__filling_ui = False
        self.__exception_thrown = False
        if epsilon is None:
            self.__epsilon = DEFAULT_EPSILON
        else:
            self.__epsilon = epsilon
        print("Policy: %s, with epsilon value: %.1f" % ("DataLossPolicy", self.__epsilon))
        self.__activity_abstract_states_already_filled = {}
        self.__activity_already_visited = []
        self.__activity_already_tested = []
        self.report_file_name = "%s/report.html" % device.output_dir
        self.activity_coverage = 0
        self.activity_tested_coverage = 0
        self.__intent_sent = False
        self.__back_done = False
        self.__activity_list = DataLossPolicy.get_activity_list(self.app)
        self.__num_step_outside_app = 0
        self.script_events = []
        self.script = None
        self.last_state = None
        self.last_event = None
        self.script_event_idx = 0
        self.current_state = None
        self.data_loss_num = 0
        self.double_rotation_num = 0
        self.fatal_exception_num = 0
        self.fillUI_num = 0
        if scroll_full_down_y is None:
            self.scroll_full_down_y = 1600
        else:
            self.scroll_full_down_y = scroll_full_down_y
        self.current_abstract_state_str = None
        self.oracle_failed = None
        self.current_activity = None

    @staticmethod
    def get_activity_list(app):
        activities = []
        for activity in app.activities:
            activity = activity[activity.rfind(".") + 1:]
            activities.append(activity)
        return activities

    def generate_event(self):

        if self.current_state is None:
            import time
            time.sleep(5)
            return KeyEvent(name="BACK")

        event = None

        current_activity = self.__get_current_foreground_activity()
        print("[INFO]   Current activity: " + current_activity)

        if current_activity in self.__activity_list and current_activity not in self.__activity_already_visited:
            self.__activity_already_visited.append(current_activity)
            self.activity_coverage = self.get_activities_coverage(self.__activity_already_visited)

        print("[INFO]   " + str(self.activity_coverage) + "% of activities have been explored.")

        # if the previous operation is not finished, continue
        if len(self.script_events) > self.script_event_idx:
            event = self.script_events[self.script_event_idx].get_transformed_event(self)
            self.script_event_idx += 1

        # First try matching a state defined in the script
        if event is None and self.script is not None:
            operation = self.script.get_operation_based_on_state(self.current_state)
            if operation is not None:
                self.script_events = operation.events
                # restart script
                event = self.script_events[0].get_transformed_event(self)
                self.script_event_idx = 1

        if event is None:
            event = self.__generate_event_based_on_data_loss_policy()

        self.last_event = event
        self.last_state = self.current_state
        return event

    def __get_current_foreground_activity(self):
        while self.current_state.foreground_activity is None:
            self.current_state = self.device.get_current_state()
            print("[WARNING} The foreground activity is None. Wait 2 seconds.")
            time.sleep(2)
        return self.current_state.foreground_activity[self.current_state.foreground_activity.rfind('.') + 1:]

    def __generate_event_based_on_data_loss_policy(self):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        current_activity = self.__get_current_foreground_activity()
        current_state = self.current_state

        if current_activity not in self.__activity_list and self.__num_step_outside_app <= MAX_NUM_STEPS_OUTSIDE:
            self.__num_step_outside_app += 1
            views = current_state.views
            for view in views:
                text = view["text"]
                if text is not None and text.encode("ascii", "ignore").lower() in self.preferred_buttons:
                    return TouchEvent(view=view)

        # it returns 0 if the app is the first app in the activity stack
        # it returns a number > 0 which represents the position of the activity in the stack
        # it returns -1 if the activity isn't in the activity stack
        if current_state.get_app_activity_depth(self.app) < 0:
            # If the app is not in the activity stack
            if not self.__intent_sent:
                print("[INFO]   The app isn't in the activity stack...trying to start it...")
                self.__intent_sent = True
                return IntentEvent(intent=self.app.get_start_intent())
            else:
                print("[WARNING]Seems that IntentEvent doesn't work...trying to go BACK")
                self.__intent_sent = False
                return KeyEvent(name="BACK")
        elif current_state.get_app_activity_depth(self.app) > 0:
            if not self.__back_done:
                print("[INFO]   The app isn't on top of the activity stack...trying to go BACK")
                self.__back_done = True
                return KeyEvent(name="BACK")
            else:
                self.__back_done = False
                print("[WARNING]Seems that BACK doesn't work...trying to send IntentEvent")
                return IntentEvent(intent=self.app.get_start_intent())
        else:
            self.__intent_sent = False
            self.__back_done = False
            self.__num_step_outside_app = 0
            self.current_activity = current_activity

        # Get all possible input events
        possible_events = current_state.get_possible_input_for_dataloss_policy()

        if current_activity not in self.__activity_abstract_states_already_filled.keys():
            self.__activity_abstract_states_already_filled[current_activity] = []
            print("[INFO]   New activity found: %s" % current_activity)

        # Create the abstract_state and check whether it already exists:
        # - if it doesn't exist, it is added as a new abstract_state
        # - if it exists, it is updated with the current possible_events
        current_abstract_state = AbstractState(possible_events)
        for abstract_state in self.__activity_abstract_states_already_filled[current_activity]:
            if current_abstract_state.equals(abstract_state):
                current_abstract_state = abstract_state
                break
        self.current_abstract_state_str = current_abstract_state.state_str
        possible_events.append(DoubleRotationEvent()) # appended here otherwise it is inserted in abstract state twice

        print("[INFO]   Current abstract state: " + self.current_abstract_state_str)

        if isinstance(self.last_event, FillUIEvent):
            return DoubleRotationEvent()

        if self.__filling_ui and isinstance(self.last_event, DoubleRotationEvent):
            self.__filling_ui = False
            if self.scroll_full_down_y is not None:
                return ScrollEvent(direction="FULL_DOWN", y_full_down=self.scroll_full_down_y)
            else:
                return ScrollEvent(direction="FULL_DOWN")

        fill_ui_event = self.__try_to_generate_fill_ui(current_activity, current_abstract_state)
        if fill_ui_event is not None:
            if current_activity not in self.__activity_already_tested:
                self.__activity_already_tested.append(current_activity)
                self.activity_tested_coverage = self.get_activities_coverage(self.__activity_already_tested)
            self.fillUI_num += 1
            return fill_ui_event

        number = random.uniform(0.0, 1.0)
        if 0.0 <= number <= float(self.__epsilon):
            unique_code_list = current_abstract_state.get_all_unique_codes_of_events()
        else:
            unique_code_list = current_abstract_state.get_unique_codes_of_events_not_already_triggered()
        event = DataLossPolicy.__generate_event_based_on_events_probability(possible_events, unique_code_list)
        current_abstract_state.set_event_as_already_triggered(event)
        return event

    def __filter_events(self, events):
        events_tmp = []
        for event in events:
            found = False
            if isinstance(event, TouchEvent) or isinstance(event, LongTouchEvent):
                for forbidden_view in self.__forbidden_views:
                    if forbidden_view in str(event.view["class"]).lower():
                        found = True
                        break
                if found:
                    continue
            for event_tmp in events_tmp:
                if event.create_unique_code() == event_tmp.create_unique_code():
                    found = True
                    break
            if not found:
                events_tmp.append(event)
        return events_tmp

    @staticmethod
    def __generate_event_based_on_events_probability(possible_events, unique_codes_list):
        num = random.randint(0, len(unique_codes_list) - 1)
        winner_event_code = unique_codes_list[num]
        for event in possible_events:
            if event.create_unique_code() == winner_event_code:
                return event

    def report(self, data_time, event=None, exception_str=None, exception_desc=""):
        if self.device.output_dir is None:
            return
        if event is None: # logcat thread always has event=None and exception_str!=None
            event = self.last_event
            self.fatal_exception_num += 1
        views = event.get_views()
        view_bounds_list = []
        for view in views:
            view_bounds_list.append(view["bounds"])
        exception_msg = ""
        time_msg = data_time
        if self.current_activity is not None:
            activity_msg = self.current_activity
        else:
            activity_msg = self.__get_current_foreground_activity()
        event_msg = event.get_event_str(self.last_state)
        view_bound_msg = str(view_bounds_list).replace(" ", "")
        view_bound_msg = view_bound_msg[1: len(view_bound_msg) - 1]
        abstract_state_msg = ""
        if self.current_abstract_state_str is not None:
            abstract_state_msg = self.current_abstract_state_str
        exception_type_msg = ""

        if exception_str is not None:
            self.__exception_thrown = True
            result_msg = "Exception"
            exception_type_msg = exception_str
            exception_msg = exception_desc
        elif not self.__exception_thrown:
            result_msg = "Ok"
        else:
            self.__exception_thrown = False
            result_msg = "Ok"

        msg = "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            time_msg, result_msg, activity_msg, event_msg, view_bound_msg, abstract_state_msg, exception_type_msg, exception_msg
        )

        DataLossPolicy.write_report_on_file(self.report_file_name, msg)

    @staticmethod
    def write_report_on_file(file_path, msg):
        if msg is None:
            return
        if file_path is None:
            return
        f = open(file_path, "a")
        f.write(msg)
        f.close()

    def get_activities_coverage(self, activity_list):
        return round(len(activity_list) * 100.0 / len(self.__activity_list))

    @staticmethod
    def create_html_report_head(file_path):
        f = open(file_path, "a")
        f.write("<html><head><style>table{font-family:arial,sans-serif;border-collapse:collapse;width:100%;}td,"
                + "th{border:1pxsolid#000000;text-align:center;padding:8px;}tr:nth-child(even){background-color:#dddddd;}</style>"
                + "</head><body><center><h1>Final report</h1><table><tr><th>TIME</th><th>RESULT</th><th>ACTIVITY</th>"
                + "<th>EVENT</th><th>VIEW BOUNDS</th><th>ABSTRACT STATE</th><th>EXCEPTION</th><th>EXCEPTION MSG</th></tr>")
        f.close()

    @staticmethod
    def create_html_report_tail(file_path, event_num, data_loss_num, fat_exc_num, activity_cov, dr_num, fu_num, start_time, end_time, activity_test):
        f = open(file_path, "a")
        f.write("</table></center><br>")
        f.write("Activities covered: %d%s<br>" % (activity_cov, "%"))
        f.write("Activities tested: %d%s<br>" % (activity_test, "%"))
        f.write("Generated events: %d<br>" % event_num)
        f.write("Genetared FillUI events: %d<br>" % fu_num)
        f.write("Generated DoubleRotation events: %d<br>" % dr_num)
        f.write("Dataloss found: %d<br>" % data_loss_num)
        f.write("Fatal exceptions thrown: %d<br>" % fat_exc_num)
        f.write("Start Time: %s<br>" % str(start_time))
        f.write("End Time: %s<br>" % str(end_time))
        f.close()

    def __try_to_generate_fill_ui(self, activity, abstract_state):
        if activity not in self.__activity_list or self.current_state.views is None:
            return
        abs_found = False
        for tmp_abstract_state in self.__activity_abstract_states_already_filled[activity]:
            if tmp_abstract_state.equals(abstract_state):
                abs_found = True
                break
        if not abs_found:
            self.__activity_abstract_states_already_filled[activity].append(abstract_state)
            self.__filling_ui = True
            return FillUIEvent(views=self.current_state.views)

    def check_data_loss(self, event, screen_before=None, screen_after=None):
        msg = ""
        views_before = View(self.last_state.views)
        views_after = View(self.current_state.views)
        if views_before.is_different_from(views_after):
            msg = "Mismatch between views"
            self.oracle_failed = "Views"
        if screen_before.is_different_from(screen_after, MAX_THRESHOLD_FOR_SCREENSHOT_COMPARISON):
            if msg == "":
                msg = "Mismatch between screenshots"
                self.oracle_failed = "Screenshots"
            else:
                msg += " and screenshots"
                self.oracle_failed = "ViewsAndScreenshots"
        if msg != "":
            self.__filling_ui = False
            raise DataLossException(
                "[WARNING]" + event.get_event_str(self.last_state) + " has generated a data loss exception. "
                + msg + ".")

    def save_data_loss_source(self, data_time, img_after=None, img_before=None):
        out_dir = self.device.output_dir
        if out_dir is None:
            return
        import os
        dir = out_dir + "/dataloss"
        if not os.path.isdir(dir):
            os.makedirs(out_dir + "/dataloss")
            os.makedirs(out_dir + "/dataloss/views")
            os.makedirs(out_dir + "/dataloss/screenshots")
            os.makedirs(out_dir + "/dataloss/views_and_screenshots")
        if self.oracle_failed == "Views":
            dir = out_dir + "/dataloss/views"
        elif self.oracle_failed == "Screenshots":
            dir = out_dir + "/dataloss/screenshots"
        elif self.oracle_failed == "ViewsAndScreenshots":
            dir = out_dir + "/dataloss/views_and_screenshots"
        file_state = open(dir + "/" + data_time + "_views.txt", "w")
        file_state.write("BEFORE: " + self.last_state.views.__str__() + "\nAFTER : " + self.current_state.views.__str__())
        file_state.close()
        if img_before is None or img_after is None:
            return
        img_after.save_img_on_file(dir + "/" + data_time + "_after.png")
        img_before.save_img_on_file(dir + "/" + data_time + "_before.png")
