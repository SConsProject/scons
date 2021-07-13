C:\\%WINPYTHON%\\python.exe --version
for /F "tokens=*" %%g in ('C:\\%WINPYTHON%\\python.exe -c "import sys; print(sys.path[-1])"') do (set PYSITEDIR=%%g)
REM use mingw 32 bit until #3291 is resolved
set PATH=C:\\%WINPYTHON%;C:\\%WINPYTHON%\\Scripts;C:\\ProgramData\\chocolatey\\bin;C:\\MinGW\\bin;C:\\MinGW\\msys\\1.0\\bin;C:\\cygwin\\bin;C:\\msys64\\usr\\bin;C:\\msys64\\mingw64\\bin;%PATH%
C:\\%WINPYTHON%\\python.exe -m pip install -U --progress-bar off pip setuptools wheel
C:\\%WINPYTHON%\\python.exe -m pip install -U --progress-bar off urllib3 coverage codecov
set STATIC_DEPS=true & C:\\%WINPYTHON%\\python.exe -m pip install -U --progress-bar off lxml
C:\\%WINPYTHON%\\python.exe -m pip install -U --progress-bar off -r requirements.txt
REM install 3rd party tools to test with
choco install --allow-empty-checksums dmd ldc swig vswhere xsltproc winflexbison
set SCONS_CACHE_MSVC_CONFIG=true
set
