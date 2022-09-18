### Kattis-Moss Package
Place python file `clean.py` or the applicable executable files in the folder of the `moss_package` folder.

If using the python file, the libraries in `requirements.txt` must be preinstalled.

The script takes one command line argument: Paste the URL of the Kattis Standing website.

``https://nus.kattis.com/courses/CS2040/<sem>/assignments/<code>/standings``

Prior to running the script, one must obtain the `./kattisrc` file from `https://nus.kattis.com/download/kattisrc` and place it either in the root directory or the `moss_package` folder to enable token-based authentication. Alternatively, if you want to login by password, add `-p` to the command line argument and manually login. Input `nus` for the Kattis Domain field.

Executable files are compiled via PyInstaller. The `exe` executable is compiled on a Windows 11,  while the Unix executable is compiled on an Intel core MacOS Mojave and may not be applicable for ARM chips.