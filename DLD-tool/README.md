# Data Loss Detector: Automatically Revealing Data Loss Bugs in Android Apps
Data Loss Detector (DLD) is a fully automatic tool able to detect Data Loss failures while exploring the app under test. 
It works via command line, both on Windows OS and on Linux OS. 
DLD exloits [Droidbot](https://github.com/honeynet/droidbot), a state-of-the-art test input generation tool for Android apps, to send to the connected Android device event sequences through which it explores the app under test, searching for Data Loss problems that may affect the app. 
Finally, it produces a detailed report containing information about the exploration performed and the 
Data Loss failures detected, also providing the possibility to reproduce them.

## Prerequisites
1) [Android SDK](https://developer.android.com/studio).

    Set the following enviroment variables:
   - ANDROID_HOME
        - On Linux OS, it should be */usr/lib/android-sdk*
        - On Windows Os, it should be *C:/Users/<your_pc_name>/AppData/Local/Android/Sdk*
   - TOOLS 
        - On Linux OS, it should be */usr/lib/android-sdk/tools*
        - On Windows Os, it should be *C:/Users/<your_pc_name>/AppData/Local/Android/Sdk/tools*
   - PLATFORM_TOOLS 
        - On Linux OS, it should be */usr/lib/android-sdk/platform-tools*
        - On Windows Os, it should be *C:/Users/<your_pc_name>/AppData/Local/Android/Sdk/platform-tools*
   - EMULATOR 
        - On Linux OS, it should be */usr/lib/android-sdk/emulator*
        - On Windows Os, it should be *C:/Users/<your_pc_name>/AppData/Local/Android/Sdk/emulator*
2) [Python](https://www.python.org/downloads/release/python-2716/) (version 2.7)
    
    On Windows OS, set the following enviroment variables:
    - PYTHON 
        - It should be *C:/Python27* 
    - PIP 
        - It should be *C:/Python27/Scripts*
    
3) [Java 8](https://www.oracle.com/technetwork/java/javase/downloads/jdk8-downloads-2133151.html). 
    
    On Windows OS, set the following enviroment variable:
    - JAVA_HOME 
        - It should be *C:/Program Files/Java/jdk1.8.0_191/bin* 

## How to install
1) **git clone https://gitlab.com/learnERC/datalosstestingtool.git**
2) **cd DLD-tool**
3) **python installer.py -install** (to uninstall DLD, use the **-uninstall** option)
   - If installer.py does not work, then install DLD manually:
      - **cd droidbot-tool**
      - **pip install -e .**
      - **cd ..**
      - **pip install -e .**
4) Check whether it is correctly installed typing **dld -h**

## How to use the tool
DLD works via command line and requires only the apk file of the app to be tested. It is not necessary to be inside the DLD folder to start the tool. It is possible to set the execution time in terms of either time in seconds or number of events to be generated. 
1) Make sure you have an Android device opened and connected via ADB (check it out typing **adb devices**)
2) Launch DLD typing **dld -a <appname.apk> -o <output_folder>**. This is the most basic command to start DLD using the default settings. 
You can add one or more customized settings:
   - **-is_emulator**: add this option if you are using an Android Virtual Device
   - **-scroll_full_down_y \<number\>**: the y coordinate on the screen from which DLD starts to swipe up (1600 by default)
   - **-main_activity <activity_name>**: the activity used by DLD to start the app. Sometimes, DLD fails to get the correct main activity from the manifest.xml of the app. For example, in the "Bee Count" app, it uses *com.knirirr.beecount..WelcomeActivity* (with two dots) instead of *com.knirirr.beecount.WelcomeActivity* (with one dot).
As a result, DLD will not be able to start the app. If this happens, specify the correct main activity with the **-main_activity** option. For example, *-main_activity com.knirirr.beecount.WelcomeActivity*
   - **-epsilon \<number\>**: a value between 0.0 to 1.0 (0.1 by default). 0.0 implies a pure systematic exploration while 1.0 
   implies a pure random exploration
   - **-timeout \<number\>**: the time in seconds to be allocated for the execution
   - **-count \<number\>**: the number of events to be generated (2250 by default)
   - **-interval \<number\>**: the sleep time among the events (3 seconds by default). Increase this value if your Android device works slowly
   - **-script <your_script.json>**: specify the json script to force DLD to execute specific actions. It is useful if the app requires, for example, a login
   - **-grant_perm**: it grants all the permissions the app requires (recommanded)
   - **-keep_app**: it does not uninstall the app after the execution of DLD
   - type **dld --help** for more details

## How to read the results
DLD reports all the information into the *output_folder* (specified with the *-o* option). In this folder, DLD creates the *report.html* file that contains detailed information about the exploration. In addition, DLD provides the *dataloss* folder, which contains all the Data Loss failures detected during the execution. They are divided into three folders, each of which corresponds to a specific oracle.  Here, each Data Loss failure is reported by 3 files:
- year_month_day_hour_minute_second_before.png, which is the screenshot taken before the double orientation change
- year_month_day_hour_minute_second_after.png, which is the screenshot taken after the double orientation change
- year_month_day_hour_minute_second_views.txt, which contains the descriptions of the views both before and after the double orientation change

Note that it exists a corrispondence between the discovery date of a specific Data Loss failure inside the *report.html* and the name of the files that represent such failure. 

## How to replay the Data Loss failures detected in a previous exploration
DLD allows to reproduce the exact event sequence generated in a previous execution, in order to reproduce the Data Loss failures detected.
Type **dld -a <appname.apk> -policy replay -replay_output <output_folder>** to start DLD in replay mode, reproducing the event sequence that leads to the Data Loss failures detected.
