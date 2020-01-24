from subprocess import call, check_output
from os import chdir
from sys import argv


def check_python_version():
    import platform
    python_version = platform.python_version()
    if python_version[0] == "2":
        return True
    print("Error: you are not using Python 2")
    return False


def exec_command(command):
    return call(command.split())


def exec_command_with_output(command):
    return check_output(command.split())


def install():
    print("Starting dld installation...")
    # change the directory to droidbot
    chdir("droidbot-tool/")
    # install droidbot via pip
    exec_command("pip install -e .")
    # change to root directory
    chdir("../")
    # install dld via pip
    exec_command("pip install -e .")
    pip_list = str(exec_command_with_output("pip list"))
    if "dld" in pip_list and "droidbot" in pip_list:
        print("Done!")
    else:
        print("Something went wrong, try again!")


def uninstall():
    print("Starting to uninstall dld...")
    exec_command("pip uninstall droidbot")
    exec_command("pip uninstall dld")
    pip_list = str(exec_command_with_output("pip list"))
    if "dld" not in pip_list and "droidbot" not in pip_list:
        print("Done!")
    else:
        print("Something went wrong, try again!")


def main(args):
    if len(args) != 2:
        print("Error: type -h for help")
        return
    cmd = args[1]
    if not check_python_version():
        return
    if cmd == "-install":
        install()
    elif cmd == "-uninstall":
        uninstall()
    elif cmd == "-h":
        print("-install: install dld")
        print("-uninstall: uninstall dld")
    else:
        print("Error: type -h for help")


if __name__ == "__main__":
    main(argv)