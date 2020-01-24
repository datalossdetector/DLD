from .utils import md5
from .input_event import DoubleRotationEvent


class AbstractState(object):

    def __init__(self, possible_event_list):
        self.abstract_views = []
        self.event_list = []
        for event in possible_event_list:
            unique_code = event.create_unique_code()
            event_dict = {"unique_code": unique_code,
                          "triggered": False}
            self.event_list.append(event_dict)
        dr = DoubleRotationEvent()
        self.event_list.append({"unique_code": dr.create_unique_code(), "triggered": True})
        self.state_str = md5(self.event_list.__str__())

    def equals(self, other):
        return self.state_str == other.state_str

    def set_event_as_already_triggered(self, event):
        unique_code = event.create_unique_code()
        for event_dict in self.event_list:
            if event_dict["unique_code"] == unique_code:
                event_dict["triggered"] = True

    def get_unique_codes_of_events_not_already_triggered(self):
        # get the unique codes of triggerable events that haven't been executed yet
        unique_codes = []
        for event_dict in self.event_list:
            if not event_dict["triggered"]:
                unique_codes.append(event_dict["unique_code"])
        # in case all the triggerable events have already been executed, restore them as not executed
        if len(unique_codes) == 0:
            for event_dict in self.event_list:
                event_dict["triggered"] = False
                unique_codes.append(event_dict["unique_code"])
        return unique_codes

    def get_all_unique_codes_of_events(self):
        # get all unique codes of triggerable events
        unique_codes = []
        for event_dict in self.event_list:
            unique_codes.append(event_dict["unique_code"])
        return unique_codes