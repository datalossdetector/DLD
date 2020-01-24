from setuptools import setup
setup(
    name="dld",
    versions="1.0.0",
    entry_points={
        'console_scripts': [
            'dld=droidbot.start:main',
        ]
    }
)