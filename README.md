# A Deep Learning-Based Experiment on Forest Wildfire Detection in Machine Vision Framework

## Overview
This project presents a real-time forest wildfire detection system using a machine vision framework. It combines computer vision techniques with IoT sensor data to improve detection accuracy and reduce false positives.

The system processes live video streams to identify fire patterns and integrates data from external sensors such as smoke, temperature, and fire detectors. It also includes location tracking and an automated alert system for rapid response.

## Features
- Real-time fire detection using image processing techniques  
- Integration with IoT sensors (fire, smoke, temperature)  
- Location tracking using GPS and IP-based methods  
- Automated alert system using Telegram  
- Web-based dashboard for monitoring  

## Technologies Used
- Python  
- Flask  
- OpenCV  
- NumPy and Pandas  
- Google Sheets API  
- Telegram Bot API  
- HTML, CSS, JavaScript  

## System Workflow
1. Capture live video using a camera  
2. Process frames using computer vision techniques  
3. Detect fire regions based on color-space analysis  
4. Retrieve data from IoT sensors  
5. Combine vision and sensor data for improved accuracy  
6. Send alerts with location details  
7. Display results on a web dashboard  

## Project Structure
app.py  
templates/  
static/  
requirements.txt  
README.md  
Project_Report.pdf  

## Installation and Setup
1. Install required dependencies:  
   pip install -r requirements.txt  

2. Run the application:  
   python app.py  

3. Open in browser:  
   http://127.0.0.1:5000  

## Results
The system successfully detects fire in real time using computer vision techniques. The integration of IoT sensors improves detection reliability and reduces false positives.

## Hardware Results
The IoT sensors (fire, smoke, temperature) successfully detect environmental conditions and send data to the system.

![Hardware Setup](images/hardware.jpg)
<img width="989" height="423" alt="image" src="https://github.com/user-attachments/assets/7260baa2-896c-4d7f-a770-2a42f4df0f56" />

<img width="436" height="489" alt="image" src="https://github.com/user-attachments/assets/9f466bba-0c20-49b5-b6b1-bcb25c3620c6" />


## Software Results
The system detects fire from live video and displays results on the dashboard interface.

![Fire Detection](images/output1.png)
<img width="526" height="512" alt="image" src="https://github.com/user-attachments/assets/344a701d-937a-4aa7-919f-9b530b07b67e" />

![Dashboard](images/output2.png)
<img width="649" height="377" alt="image" src="https://github.com/user-attachments/assets/b6aa3c1a-6878-4d25-8a1d-eebab2c37892" />
<img width="621" height="404" alt="image" src="https://github.com/user-attachments/assets/5c7ed80b-7682-42e9-b7d6-5c8f46533cbd" />

## Future Scope
- Integration of deep learning models for improved accuracy  
- Deployment on cloud platforms  
- Mobile application development  
- Drone-based monitoring systems  

## Author
Nirmitha H
