from setuptools import setup

setup(
    name="uv_shebang_demo",
    version="0.1.0",
    packages=["uv_shebang_demo"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/uv_shebang_demo"]),
        ("share/uv_shebang_demo", ["package.xml"]),
        ("share/uv_shebang_demo/launch", ["launch/probe.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Decwest",
    maintainer_email="fumiyaonishi1016@gmail.com",
    description="ROS virtual-environment interpreter probe",
    license="Apache-2.0",
    entry_points={"console_scripts": ["probe = uv_shebang_demo.probe:main"]},
)
