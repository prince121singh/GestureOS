# 🖐️ GestureOS

### AI-Powered Touchless Desktop Control System

> **Control your Windows desktop with your hands — naturally, intelligently, and in real time.**

GestureOS is a modern **computer-vision powered desktop interaction system** built with Python, MediaPipe, OpenCV, and PySide6. It transforms a standard webcam into a touchless control interface, allowing users to move the cursor, click, scroll, control system actions, and customize gestures using natural hand movements.

Designed with a **premium desktop UI, real-time telemetry, gesture calibration, persistent profiles, and modular architecture**, GestureOS combines computer vision with practical desktop automation.

---

## ✨ Highlights

<table>
<tr>
<td>🖐️ <b>Hand Tracking</b><br>Real-time landmark detection</td>
<td>🖱️ <b>Mouse Control</b><br>Touchless cursor interaction</td>
<td>🎯 <b>Calibration</b><br>Personalized recognition</td>
</tr>
<tr>
<td>📊 <b>Telemetry</b><br>Confidence, stability & FPS</td>
<td>🎨 <b>Premium UI</b><br>Modern PySide6 interface</td>
<td>⚙️ <b>Remapping</b><br>Custom gesture actions</td>
</tr>
</table>

---

## 🚀 Core Features

### 🖐️ Computer Vision

* Real-time hand detection
* MediaPipe Hand Landmarker integration
* Hand landmark tracking
* Gesture recognition pipeline
* Gesture confidence measurement
* Gesture stability analysis
* Real-time FPS monitoring

### 🖱️ Touchless Desktop Control

* Cursor movement using hand gestures
* Gesture-based left click
* Gesture-based scrolling
* Volume control
* Screenshot action
* Media/pause control
* Configurable gesture actions

### 🎯 Smart Calibration

GestureOS includes a dedicated calibration system that adapts recognition thresholds based on collected samples.

The calibration pipeline:

```text
Gesture
   ↓
Sample Collection
   ↓
Confidence Analysis
   ↓
Stability Analysis
   ↓
Personalized Threshold
   ↓
Persistent Calibration Profile
```

Calibration data is saved locally so your personalized settings can be restored when the application starts again.

---

# 🖐️ Gesture Controls

|        Gesture        | Default Action        |
| :-------------------: | --------------------- |
|      ☝️ **Point**     | Move Cursor           |
|      🤏 **Pinch**     | Left Click            |
|      ✌️ **Peace**     | Scroll                |
|    👍 **Thumb Up**    | Volume Up             |
|   👎 **Thumb Down**   | Volume Down           |
|       ✊ **Fist**      | Screenshot            |
|    ✋ **Open Palm**    | Pause / Media Control |
|    🤟 **Rock Sign**   | Configurable          |
| 🖐️ **Three Fingers** | Configurable          |

> Gesture actions are designed to be configurable through the GestureOS interface.

---

# 🧠 System Architecture

GestureOS follows a modular real-time processing pipeline:

```text
                 ┌─────────────────┐
                 │     Webcam      │
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │     OpenCV      │
                 │ Frame Capture   │
                 └────────┬────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ MediaPipe Hand        │
              │ Landmarker            │
              └───────────┬───────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Gesture Engine  │
                 └────────┬────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      ┌───────────────┐       ┌───────────────┐
      │  Confidence   │       │   Stability   │
      └───────┬───────┘       └───────┬───────┘
              │                       │
              └───────────┬───────────┘
                          ▼
                 ┌─────────────────┐
                 │ Action Controller│
                 └────────┬────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ Windows Desktop │
                 └─────────────────┘
```

---

# 🛠️ Technology Stack

### Programming

![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square\&logo=python\&logoColor=white)

### Computer Vision

![OpenCV](https://img.shields.io/badge/OpenCV-Computer_Vision-5C3EE8?style=flat-square\&logo=opencv\&logoColor=white)

![MediaPipe](https://img.shields.io/badge/MediaPipe-Hand_Tracking-FF6F00?style=flat-square)

### Desktop Application

![PySide6](https://img.shields.io/badge/PySide6-Qt_Desktop_App-41CD52?style=flat-square\&logo=qt\&logoColor=white)

### Data / Processing

![NumPy](https://img.shields.io/badge/NumPy-Numerical_Computing-013243?style=flat-square\&logo=numpy\&logoColor=white)

---

# 📁 Project Structure

```text
GestureOS/
│
├── app.py
├── camera_test.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── assets/
│   └── style.css
│
├── core/
│   ├── camera_engine.py
│   ├── calibration_manager.py
│   ├── calibration_ui.py
│   ├── config.py
│   ├── controller.py
│   ├── gesture_engine.py
│   ├── hand_tracker.py
│   └── ...
│
├── models/
│   └── hand_landmarker.task
│
├── utils/
│   └── helpers.py
│
└── config/
    └── calibration_profile.json
```

---

# ⚙️ Installation

## 1. Clone the Repository

```bash
git clone https://github.com/prince121singh/GestureOS.git
cd GestureOS
```

## 2. Create Virtual Environment

### Windows

```powershell
python -m venv .venv
```

## 3. Activate Environment

```powershell
.venv\Scripts\activate
```

## 4. Install Dependencies

```powershell
pip install -r requirements.txt
```

---

# ▶️ Run GestureOS

Start the application:

```powershell
python app.py
```

Make sure:

* Your webcam is connected
* Camera permissions are enabled
* Your hand is visible inside the camera frame
* The environment is properly activated

---

# 🎯 Calibration System

GestureOS provides user-specific gesture calibration.

### Calibration Process

```text
Select Gesture
      ↓
Start Calibration
      ↓
Perform Gesture
      ↓
Collect Samples
      ↓
Analyze Confidence
      ↓
Analyze Stability
      ↓
Calculate Threshold
      ↓
Save Profile
```

The calibration profile is stored locally:

```text
config/calibration_profile.json
```

This allows calibrated thresholds to persist across application sessions.

---

# 🎨 Premium Desktop Interface

GestureOS uses a custom **PySide6 + QSS** interface with a modern dark desktop aesthetic.

The interface includes:

* 🎥 Live camera preview
* 📊 Real-time telemetry
* 🎯 Gesture confidence
* 📈 Stability monitoring
* ⚡ FPS monitoring
* 🖱️ Control status
* 🎛️ Gesture remapping
* 🎯 Calibration controls
* 📜 Activity history
* 🔔 Toast notifications
* 🖥️ System tray support

The UI styling is separated from the application logic:

```text
assets/style.css
```

This keeps visual changes independent from the core gesture-control system.

---

# 📊 Real-Time Telemetry

GestureOS monitors important runtime information including:

| Metric           | Purpose                        |
| ---------------- | ------------------------------ |
| FPS              | Camera processing performance  |
| Confidence       | Gesture recognition confidence |
| Stability        | Gesture consistency            |
| Current Gesture  | Detected gesture               |
| Action           | Current desktop action         |
| Controller State | Control system status          |

This makes it easier to understand and tune real-time gesture recognition.

---

# 🔧 Configuration

GestureOS is designed with configurable components so that gesture thresholds, actions, and application behavior can be customized without rebuilding the entire system.

Configuration and calibration data can be maintained locally within the project.

---

# 🔒 Privacy

GestureOS is designed around **local processing**.

The core gesture-recognition pipeline processes the webcam feed on the user's machine rather than requiring a cloud computer-vision service.

> Camera access is required while using GestureOS.

---

# ⚡ Performance

GestureOS is designed for real-time interaction with an emphasis on:

* Low-latency gesture processing
* Smooth cursor movement
* Efficient camera processing
* Stable gesture detection
* Responsive desktop controls
* Continuous telemetry

Actual performance depends on hardware, camera quality, lighting, and system workload.

---

# 📸 Screenshots

Project screenshots can be added here:

```text
screenshots/
├── dashboard.png
├── calibration.png
├── gesture-control.png
└── telemetry.png
```

Example:

```markdown
![GestureOS Dashboard](screenshots/dashboard.png)
```

---

# 🎬 Demo

> Add a short demo GIF or video here after recording the final GestureOS workflow.

Example:

```markdown
![GestureOS Demo](screenshots/gestureos-demo.gif)
```

---

# 🧪 Testing

Basic application testing can be performed using:

```powershell
python camera_test.py
```

For the main application:

```powershell
python app.py
```

Recommended testing areas:

* Camera initialization
* Hand detection
* Gesture recognition
* Cursor movement
* Click interaction
* Scrolling
* Calibration
* Gesture remapping
* UI responsiveness

---

# 🗺️ Roadmap

### ✅ Completed

* [x] Real-time hand tracking
* [x] Gesture recognition
* [x] Cursor control
* [x] Gesture click
* [x] Gesture scrolling
* [x] System actions
* [x] Gesture calibration
* [x] Persistent calibration
* [x] Gesture remapping
* [x] Premium PySide6 interface
* [x] External QSS styling
* [x] Telemetry dashboard
* [x] System tray integration

### 🔮 Future

* [ ] Application-specific gesture profiles
* [ ] Multi-monitor optimization
* [ ] More advanced gesture recognition
* [ ] Multi-hand interaction
* [ ] Adaptive gesture learning
* [ ] Voice + gesture hybrid control
* [ ] More desktop automation actions
* [ ] Windows standalone executable
* [ ] Performance optimization
* [ ] Expanded accessibility controls

---

# 💡 Why GestureOS?

Traditional desktop interaction depends heavily on physical input devices such as a mouse and keyboard.

GestureOS explores an alternative interaction model:

> **What if your hand could become the controller?**

By combining computer vision, gesture recognition, and desktop automation, GestureOS turns an ordinary webcam into an experimental touchless human-computer interface.

---

# 👨‍💻 Author

## Prince Kumar

**Full Stack Developer • AI/ML • Data Science**

I build practical software projects combining web development, artificial intelligence, machine learning, computer vision, and modern user interfaces.

### Connect

* 🐙 GitHub: [@prince121singh](https://github.com/prince121singh)
* 💼 LinkedIn: [Prince Kumar](https://www.linkedin.com/in/prince-kumar-b7868a2a7/)

---

# ⭐ Support

If you find **GestureOS** interesting, useful, or inspiring:

⭐ **Star the repository**

🍴 **Fork the project**

💡 **Suggest an improvement**

🐛 **Report an issue**

---

## 📄 License

This project is currently provided for **educational and portfolio purposes**.

---

<div align="center">

### 🖐️ GestureOS

**Touchless. Intelligent. Real-Time.**

Built with ❤️ using Python, OpenCV, MediaPipe & PySide6.

</div>
