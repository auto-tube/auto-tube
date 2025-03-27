from setuptools import setup, find_packages

setup(
    name="video_clipper",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "click",
        "ffmpeg-python",
        "opencv-python",
        "numpy",
        "tqdm"
    ],
    entry_points={
        "console_scripts": [
            "video-clipper=video_clipper:process_videos"
        ]
    }
)
