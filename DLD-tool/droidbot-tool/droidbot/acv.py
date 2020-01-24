import subprocess
import os
import time

MAX_WAIT_FOR_LOCK_FILE = 5


class ACV(object):

    def __init__(self, apk_path, output_dir):
        self.original_apk_path = apk_path
        self.output_dir = output_dir
        self.__apk_path = ACV.__modify_apk_path(self.original_apk_path)
        self.working_dir = os.path.expanduser("~") + "/acvtool/acvtool_working_dir/"
        if self.original_apk_path != self.__apk_path:
            os.rename(self.original_apk_path, self.__apk_path)
        self.is_instrumentation_running = False
        self.pickle_path = None

    @staticmethod
    def __modify_apk_path(apk_path):
        new_apk_path = apk_path
        if " " in apk_path:
            new_apk_path = apk_path.replace(" ", "_")
        return new_apk_path

    @staticmethod
    def run_cmd(cmd):
        exit_code = subprocess.call(cmd.split())
        time.sleep(2)
        return exit_code

    @staticmethod
    def run_cmd_with_output(cmd):
        out = subprocess.check_output(cmd.split())
        time.sleep(2)
        return out

    def __grant_storage_permission(self, package_name):
        read_storage_cmd = "adb shell pm grant %s android.permission.READ_EXTERNAL_STORAGE" % package_name
        ACV.run_cmd(read_storage_cmd)

        write_storage_cmd = "adb shell pm grant %s android.permission.WRITE_EXTERNAL_STORAGE" % package_name
        ACV.run_cmd(write_storage_cmd)

    def get_instrumented_apk_path(self):
        print("[INFO]: ACVTool: Waiting until the apk is instrumented.")
        if os.path.isdir(self.working_dir):
            print("[WARNING]: ACVTool: the working directory " + self.working_dir + " already exists. Please delete/move it and try again.")
            return
        exit_status = ACV.run_cmd("acv instrument " + self.__apk_path)
        if exit_status != 0:
            print("[WARNING]: ACVTool: something went wrong during the instrumentation of the app.")
            return
        if self.__apk_path != self.original_apk_path:
            os.rename(self.__apk_path, self.original_apk_path)
        app_name = "instr_" + self.__apk_path[self.__apk_path.rfind("/") + 1:]
        self.pickle_path = self.working_dir + "metadata/" + self.__apk_path[self.__apk_path.rfind("/") + 1:self.__apk_path.rfind(".")] + ".pickle"
        self.__apk_path = self.working_dir + app_name
        return self.__apk_path

    def install_apk(self):
        cmd = "acv install %s" % self.original_apk_path
        exit_status = ACV.run_cmd(cmd)
        time.sleep(2)

    def start_to_instrument_apk(self, apk_package_name):
        self.__grant_storage_permission(apk_package_name)
        cmd = "adb shell am instrument -e coverage true %s/tool.acv.AcvInstrumentation" % apk_package_name
        exit_status = ACV.run_cmd(cmd)
        if exit_status != 0:
            print("[WARNING]: ACVTool: something went wrong while starting to instrument the app. " +
                  "Droidbot will analyze the app without producing details about the code coverage")
            return
        if not self.__lock_file_exist(apk_package_name):
            print("[WARNING]: ACVTool: something went wrong while creating %s.lock file. The coverage report won't be created." % apk_package_name)
        else:
            self.is_instrumentation_running = True

    def __coverage_file_is_locked(self, apk_package_name):
        cmd = "adb shell \"test -e /mnt/sdcard/%s.lock > /dev/null 2>&1 && echo '1' || echo '0'\"" % apk_package_name
        locked = subprocess.check_output(cmd, shell=True).replace("\n","").replace("\r", "")
        return locked == '1'

    def __ec_files_exist(self, apk_package_name):
        cmd = 'adb shell ls "/mnt/sdcard/%s/"' % apk_package_name
        all_pulled_files = subprocess.check_output(cmd.split())

        coverage_file_paths = ["/mnt/sdcard/%s/" % apk_package_name + f
                               for f in all_pulled_files.split() if f.endswith(".ec")]

        if coverage_file_paths is None or len(coverage_file_paths) == 0:
            return False
        return True

    def __lock_file_exist(self, apk_package_name):
        cmd = 'adb shell ls "/mnt/sdcard/"'
        iterations = 0
        while iterations < MAX_WAIT_FOR_LOCK_FILE:
            if apk_package_name + ".lock" in ACV.run_cmd_with_output(cmd):
                return True
            else:
                print("[INFO] ACVTool: waiting until %s.lock is created" % apk_package_name)
            iterations += 1
        return False

    def stop_to_instrument_apk(self, apk_package_name):
        if not self.is_instrumentation_running:
            return

        cmd = "adb shell am broadcast -a tool.acv.finishtesting"
        exit_status = ACV.run_cmd(cmd)

        if exit_status != 0:
            print("[WARNING]: ACVTool: something went wrong while stopping to instrument the app.")
            return

        if not self.__ec_files_exist(apk_package_name):
            print("[WARNING]: ACVTool: the final coverage report can't be created, because *.ec files don't exist.")
            return

        locked = True
        while locked:
            print("[INFO]: ACVTool: Wait until the coverage file is saved.")
            locked = self.__coverage_file_is_locked(apk_package_name)
            if locked:
                time.sleep(5)
        self.__create_report(apk_package_name)

    def __create_report(self, apk_package_name):
        print("[INFO] ACVTool: Wait until final code coverage report is created.")
        cmd = "acv report %s -p %s" % (apk_package_name, self.pickle_path)
        exit_status = ACV.run_cmd(cmd)
        if exit_status != 0:
            print("[WARNING]: ACVTool: something went wrong while generating the final code coverage report.")
            return
        import shutil
        shutil.move(self.working_dir + "/report", self.output_dir)
        print("Final code coverage report is located at %s/report" % self.output_dir)
