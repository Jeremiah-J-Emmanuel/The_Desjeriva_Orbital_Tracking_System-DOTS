#!/usr/bin/env bash

clear
echo "________________Welcome to the DesJerIva Orbital Tracking System(D.O.T.S.)🛰️_______________"
echo "If you wish to exit the app, please press CTRL +C for both windows and mac"
echo "Loading..."


#The function for exiting the app
exit_app() {
    clear
    echo "Exiting app now..."
    echo "Thank you for using D.O.T.S.🛰️"
    sleep 2
    clear
    exit  0
}

trap exit_app SIGINT

# Download the TLE file
if curl -s https://celestrak.org/NORAD/elements/gp.php?GROUP=stations -o tle.txt; then
    clear

    while true; do
        echo "================== The DesJerIva Orbital Tracking System =================="
        echo "Available Satellites:"
        echo "---------------------------------------------------------"
        awk 'NR % 3 == 1' tle.txt  # Print every 3rd line starting from line 1 (satellite names)

        read -p "Which satellite do you want to track? Enter the exact name: " sat_name

        # Extract satellite TLE lines into selected_tle
        awk -v name="$sat_name" 'index($0, name) > 0 {print; getline; print; getline; print}' tle.txt > selected_tle

        # Check if we successfully got 3 lines
        # Input Validation using while Loop

        line_count=$(wc -l < selected_tle)
        if [ "$line_count" -ne 3 ]; then
            echo "Satellite not found or name not entered exactly. Please try again."
            sleep 1
            rm -f selected_tle #To reset the selected_tle file
            awk -v name="$sat_name" 'index($0, name) > 0 {print; getline; print; getline; print}' tle.txt > selected_tle
            clear

        else
            echo "Satellite '$sat_name' selected."
            echo "---------------------------------------------------------"
            echo "Satellite Data:"
            cat selected_tle
            break
        fi
    done


else
    echo "Download failed! Please check your internet connection and try again."

fi