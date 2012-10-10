#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2012, the IEP development team
#
# IEP is distributed under the terms of the (new) BSD License.
# The full license can be found in 'license.txt'.

""" Package iep

IEP (pronounced as 'eep') is a cross-platform Python IDE focused on
interactivity and introspection, which makes it very suitable for
scientific computing. Its practical design is aimed at simplicity and
efficiency.

IEP is written in Python 3 and Qt. Binaries are available for Windows,
Linux, and Mac. For questions, there is a discussion group.

Two components + tools
----------------------

IEP consists of two main components, the editor and the shell, and uses
a set of pluggable tools to help the programmer in various ways. Some
example tools are source structure, project manager, interactive help,
and workspace.

Some key features
-----------------

  * Powerful *introspection* (autocompletion, calltips, interactive help)
  * Allows various ways to *run code interactively* or to run a file as a
    script.
  * The shells runs in a *subprocess* and can therefore be interrupted or
    killed.
  * *Multiple shells* can be used at the same time, and can be of different
    Python versions (from v2.4 to 3.x, including pypy)
  * Support for using several *GUI toolkits* interactively: PySide, PyQt4,
    wx, fltk, GTK, Tk.
  * Supports *magic commands* similar to IPython.
  * *Full Unicode support* in both editor and shell.
  * Various handy *tools*, plus the ability to make your own.
  * Matlab-style *cell notation* to mark code sections (by starting a line
    with '##').
  * Highly customizable using the menu.

"""

# Set version number
__version__ = '3.0'


import sys, os
from pyzolib import ssdf, paths
from iep.codeeditor.qt import QtCore, QtGui

# Import yoton as an absolute package
from iep import yotonloader


## Define some functions


# todo: move some stuff out of this module ...

def getResourceDirs():
    """ getResourceDirs()
    Get the directories to the resources: (iepDir, appDataDir).
    Also makes sure that the appDataDir has a "tools" directory and
    a style file.
    """
    
#     # Get root of the IEP code. If frozen its in a subdir of the app dir 
#     iepDir = paths.application_dir()
#     if paths.is_frozen():
#         iepDir = os.path.join(iepDir, 'source')
    iepDir = os.path.abspath(os.path.dirname(__file__))
    if '.zip' in iepDir:
        raise RuntimeError('The IEP package cannot be run from a zipfile.')
    
    # Get where the application data is stored (use old behavior on Mac)
    # todo: quick solution until I release a new pyzolib
    try:
        appDataDir = paths.appdata_dir('iep', roaming=True, macAsLinux=True)
    except Exception:
        appDataDir = paths.appdata_dir('iep', roaming=True)
    
    # Create tooldir if necessary
    toolDir = os.path.join(appDataDir, 'tools')
    if not os.path.isdir(toolDir):
        os.mkdir(toolDir)
    
    return iepDir, appDataDir


def resetConfig(preserveState=True):
    """ resetConfig()
    Replaces the config fyle with the default and prevent IEP from storing
    its config on the next shutdown.
    """ 
    # Get filenames
    configFileName1 = os.path.join(iepDir, 'resources', 'defaultConfig.ssdf')
    configFileName2 = os.path.join(appDataDir, 'config.ssdf')        
    # Read, edit, write
    tmp = ssdf.load(configFileName1)
    if preserveState:
        tmp.state = config.state
    ssdf.save(configFileName2, tmp)    
    global _saveConfigFile
    _saveConfigFile = False
    print("Replaced config file. Restart IEP to revert to the default config.")


def loadConfig(defaultsOnly=False):
    """ loadConfig(defaultsOnly=False)
    Load default configuration file and that of the user (if it exists).
    Any missing fields in the user config are set to the defaults. 
    """ 
    
    # Function to insert names from one config in another
    def replaceFields(base, new):
        for key in new:
            if key in base and isinstance(base[key], ssdf.Struct):                
                replaceFields(base[key], new[key])
            else:
                base[key] = new[key]
    
    # Reset our iep.config structure
    ssdf.clear(config)
    
    # Load default and inject in the iep.config
    fname = os.path.join(iepDir, 'resources', 'defaultConfig.ssdf')
    defaultConfig = ssdf.load(fname)
    replaceFields(config, defaultConfig)
    
    # Platform specific keybinding: on Mac, Ctrl+Tab (actually Cmd+Tab) is a system shortcut
    if sys.platform == 'darwin':
        config.shortcuts2.view__select_previous_file = 'Alt+Tab,'
    
    # Load user config and inject in iep.config
    fname = os.path.join(appDataDir, "config.ssdf")
    if os.path.isfile(fname):
        userConfig = ssdf.load(fname)
        replaceFields(config, userConfig)


def saveConfig():
    """ saveConfig()
    Save all configureations to file. 
    """ 
    
    # Let the editorStack save its state 
    if editors:
        editors.saveEditorState()
    
    # Let the main window save its state 
    if main:
        main.saveWindowState()
    
    # Store config
    if _saveConfigFile:
        ssdf.save( os.path.join(appDataDir, "config.ssdf"), config )


class Translation(str):
    """ Derives from str class. The translate function returns an instance
    of this class and assigns extra atrributes:
      * original: the original text passed to the translation
      * tt: the tooltip text 
      * key: the original text without tooltip (used by menus as a key)
    
    We adopt a simple system to include tooltip text in the same
    translation as the label text. By including ":::" in the text,
    the text after that identifier is considered the tooltip.
    The text returned by the translate function is always the 
    string without tooltip, but the text object has an attribute
    "tt" that stores the tooltip text. In this way, if you do not
    use this feature or do not know about this feature, everything
    keeps working as expected.
    """
    pass

def translate(context, text, disambiguation=None):  
    def splitMainAndTt(s):
        if ':::' in s:
            parts = s.split(':::', 1)
            return parts[0].rstrip(), parts[1].lstrip()
        else:
            return s, ''
    
    # Get translation and split tooltip
    newtext = QtCore.QCoreApplication.translate(context, text, disambiguation)
    s, tt = splitMainAndTt(newtext)
    # Create translation object (string with extra attributes)
    translation = Translation(s)
    translation.original = text
    translation.tt = tt
    translation.key = splitMainAndTt(text)[0].strip()
    return translation


def setLanguage(languageId):
    """ setLanguage(languageId)
    Set the language for the app. Loads qt and iep translations.
    Returns the QLocale instance to pass to the main widget.
    """
    
    # Derive name, locale, and locale language name
    languageName = QtCore.QLocale.languageToString(languageId)
    locale = QtCore.QLocale(languageId)
    localeName = locale.name().split('_')[0]
    
    # Get paths were language files are
    qtTransPath = str(QtCore.QLibraryInfo.location(
                    QtCore.QLibraryInfo.TranslationsPath))
    iepTransPath = os.path.join(iepDir, 'resources')
     
    # Set Qt translations
    # Note that the translator instances must be stored
    # Note that the load() method is very forgiving with the file name
    QtCore._translators = []
    for what, where in [('qt', qtTransPath),('iep', iepTransPath)]:
        trans = QtCore.QTranslator()
        success = trans.load(what + '_' + localeName + '.tr', where)
        print('loading %s %s: %s' % (what, languageName, ['failed', 'ok'][success]))
        if success:
            QtGui.QApplication.installTranslator(trans)
            QtCore._translators.append(trans)
    
    return locale


def startIep():
    """ startIep()
    Run IEP.
    """
    
    # Do some imports
    from iep.iepcore import iepLogging # to start logging asap
    from iep.iepcore.main import MainWindow
    
    # Set to be aware of the systems native colors, fonts, etc.
    QtGui.QApplication.setDesktopSettingsAware(True)
    
    #Prevent loading plugins form the users' plugin dir since
    #this may cause multiple versions of the Qt library to be loaded
    #at once, which will conflict
    QtGui.QApplication.setLibraryPaths([])
    
    # Instantiate the application, and the main window
    QtGui.qApp = QtGui.QApplication([])
    
    # Choose language, get locale
    # todo: Turn back on so we can find all strings that we should translate
    # Also implement way to allow user to select the language
    locale = None
    #locale = setLanguage(QtCore.QLocale.Dutch)
    
    # Create IEP, using the selected locale
    frame = MainWindow(None, locale)
    
    # Enter the main loop
    QtGui.qApp.exec_()


## Init

# List of names that are later overriden (in main.py)
editors = None # The editor stack instance
shells = None # The shell stack instance
main = None # The mainwindow
icon = None # The icon 
parser = None # The source parser
status = None # The statusbar (or None)

# Get directories of interest
iepDir, appDataDir = getResourceDirs()

# Whether the config file should be saved
_saveConfigFile = True

# Create ssdf in module namespace, and fill it
config = ssdf.new()
loadConfig()

# Init default style name (set in main.restoreIepState())
defaultQtStyleName = ''

