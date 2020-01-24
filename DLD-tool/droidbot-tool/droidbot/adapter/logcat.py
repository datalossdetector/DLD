import subprocess
import logging
import time

#from wadllib.tests import data

from .adapter import Adapter
import re

class Logcat(Adapter):
    """
    A connection with the target device through logcat.
    """

    def __init__(self, device=None):
        """
        initialize logcat connection
        :param device: a Device instance
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        if device is None:
            from droidbot.device import Device
            device = Device()
        self.device = device
        self.connected = False
        self.process = None
        if device.output_dir is None:
            self.out_file = None
        else:
            self.out_file = "%s/logcat.txt" % device.output_dir
        self.__exception_found = False
        self.__exception_line = 0

    def connect(self):
        self.device.adb.run_cmd("logcat -c")
        self.process = subprocess.Popen(["adb", "-s", self.device.serial, "logcat", "-v", "threadtime"],
                                        stdin=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        stdout=subprocess.PIPE)
        import threading
        listen_thread = threading.Thread(target=self.handle_output)
        listen_thread.start()

    def disconnect(self):
        self.connected = False
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def check_connectivity(self):
        return self.connected

    def handle_output(self):
        self.connected = True

        f = None
        if self.out_file is not None:
            f = open(self.out_file, 'w')

        while self.connected:
            if self.process is None:
                continue
            line = self.process.stdout.readline()
            if not isinstance(line, str):
                line = line.decode()
            self.parse_line(line)
            if f is not None:
                f.write(line)
        if f is not None:
            f.close()
        print("[CONNECTION] %s is disconnected" % self.__class__.__name__)

    def parse_line(self, logcat_line):
        if "FATAL EXCEPTION" in logcat_line:
            self.__exception_found = True
            print("[EXCEPTION]: A fatal excepion has been thrown from the app.")
        if self.__exception_found:
            self.__exception_line += 1
        if self.__exception_line == 3:
            from droidbot.droidbot import DroidBot
            from droidbot.input_policy import DataLossPolicy
            policy = DroidBot.get_instance().input_manager.policy
            if isinstance(policy, DataLossPolicy):
                exception_start_pos = logcat_line.index("AndroidRuntime: ")
                logcat_line = logcat_line[exception_start_pos + len("AndroidRuntime:"):]
                logcat_line = re.sub('\s+',' ',logcat_line)
                data_time = time.strftime("%Y-%m-%d %H-%M-%S")
                policy.report(data_time=data_time, exception_str=logcat_line)
            self.__exception_found = False
            self.__exception_line = 0

