# forest-wildfire-detection-ml
A deep learning-based forest wildfire detection system using computer vision, IoT sensors, and real-time location tracking for early fire alerting.
# A Deep Learning-Based Experiment on Forest Wildfire Detection in Machine Vision Framework

## Overview
This project presents a real-time forest wildfire detection system using a machine vision framework. It integrates computer vision techniques with IoT sensor data to improve detection accuracy and minimize false positives.

The system analyzes live video streams to detect fire patterns and combines the results with environmental sensor data such as smoke, temperature, and fire sensors. It also includes location tracking and an automated alert mechanism for timely response.

## Features
- Real-time fire detection using image processing
- Integration with IoT sensors (fire, smoke, temperature)
- Location tracking using GPS and IP-based methods
- Automated alert system using Telegram
- Web-based monitoring dashboard

## Technologies Used
- Python
- Flask
- OpenCV
- NumPy and Pandas
- Google Sheets API
- Telegram Bot API
- HTML, CSS, JavaScript

## System Workflow
1. Capture video from camera
2. Process frames using computer vision techniques
3. Detect fire-like regions based on color analysis
4. Retrieve sensor data from IoT devices
5. Combine results for improved accuracy
6. Trigger alerts with location details
7. Display status on web dashboard

## Project Structure
project-folder/
│── app.py  
│── templates/  
│── static/  
│── requirements.txt  
│── README.md  
│── Project_Report.pdf  

## Installation and Setup
1. Install required libraries:
   pip install -r requirements.txt

2. Run the application:
   python app.py

3. Open in browser:
   http://127.0.0.1:5000

## Results
The system successfully detects fire in real time and improves reliability by combining computer vision with sensor data. Alerts are generated with location information for faster response.

## Future Scope
- Integration of deep learning models for higher accuracy
- Deployment on cloud platforms
- Mobile application support
- Integration with drone-based monitoring systems

## Author
Nirmitha H
