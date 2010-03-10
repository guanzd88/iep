""" Module baseTextCtrl.
Defines the base text control to be inherited by the shell and editor
classes. Implements styling, introspection and a bit of other stuff that
is common for both shells and editors.
"""

from introspection import doAutocomplete
import iep
import os, sys, time
import ssdf

from PyQt4 import QtCore, QtGui
from PyQt4 import Qsci
qt = QtGui

# get config
config = iep.config.editor

# define fontnames
if 'win' in sys.platform:
    FACES = {'serif': 'Times New Roman', 'mono': 'Courier New', 'sans': 'Arial'}
elif 'mac' in sys.platform:
    FACES = {'serif': 'Lucida Grande', 'mono': 'Monaco', 'sans': 'Geneva'}
else:
    FACES = {'serif': 'Times', 'mono': 'Courier', 'sans': 'Helvetica'}

# define style stuff
subStyleStuff = {   'face': Qsci.QsciScintillaBase.SCI_STYLESETFONT,
                    'fore': Qsci.QsciScintillaBase.SCI_STYLESETFORE,
                    'back': Qsci.QsciScintillaBase.SCI_STYLESETBACK,
                    'size': Qsci.QsciScintillaBase.SCI_STYLESETSIZE,
                    'bold': Qsci.QsciScintillaBase.SCI_STYLESETBOLD,
                    'italic': Qsci.QsciScintillaBase.SCI_STYLESETITALIC,
                    'underline': Qsci.QsciScintillaBase.SCI_STYLESETUNDERLINE}

def normalizePath(path):
    """ Normalize the path given. 
    All slashes will be made the same (and doubles removed)
    The real case as stored on the file system is recovered.
    Returns None on error.
    """
    
    # normalize
    path = os.path.abspath(path)  # make sure it is defined from the drive up
    path = os.path.normpath(path).lower() # make all os.sep (slashes \\ on win)
    
    # split in parts
    parts = path.split(os.sep)
    sep = '/'
    
    # make a start
    drive, tmp = os.path.splitdrive(path)
    if drive:
        # windows
        fullpath = drive.upper() + sep
        parts = parts[1:]
    else:
        # posix/mac
        fullpath = sep + parts[1] + sep
        parts = parts[2:] # as '/dev/foo/bar' becomes ['','dev','bar']
    
    for part in parts:
        # print( fullpath,part)
        options = [x for x in os.listdir(fullpath) if x.lower()==part]
        if len(options) > 1:
            print("Error normalizing path: Ambiguous path names!")
            return None
        elif len(options) < 1:
            print("Invalid path: "+fullpath+part)
            return None
        fullpath += options[0] + sep
    
    # remove last sep
    return fullpath[:-len(sep)]


# valid chars to make a name
namechars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789"
namekeys = [ord(i) for i in namechars]


# todo: a regexp on the reverse string?
def parseLine_autocomplete(text):
    """ Given a line of code (from start to cursor position) 
    returns a tuple (base, name).    
    autocomp_parse("eat = banan") -> "", "banan"
      ...("eat = food.fruit.ban") -> "food.fruit", "ban"
    When no match found, both elements are an empty string.
    """
    
    # is the line commented? The STC_P is 0 in commented lines...
    i = text.rfind("#")
    if i>=0 and text[:i].count("\"") % 2==0 and text[:i].count("\'") % 2==0:
        return "",""
        
    i_base = 0
    for i in range(len(text)-1,-1,-1):
        c = text[i]
        
        if c=='.':
            if i_base==0:
                i_base = i        
        elif c in ["'", '"']:
            # a string                
            if i_base == i+1: # dot after it
                return "''", text[i_base+1:]
            else:
                return "",""
        elif c==']':
            # may be a list
            if i_base == i+1 and i>0 and text[i-1]=='[': 
                return "[]", text[i_base+1:]
            else:
                return "",""            
        elif not c in namechars:
            break
    else:
        # we need to decrease this extra bit when the loop fully unrolled
        i-=1 
        
    # almost done...
    if i_base == 0:
        return "", text[i+1:]
    else:
        return text[i+1:i_base], text[i_base+1:]


class StyleManager(QtCore.QObject):
    """ Singleton class for managing the styles of the text control. """
    
    styleUpdate = QtCore.pyqtSignal()
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self._filename = os.path.join(iep.path, 'styles.ssdf')
        if not os.path.isfile(self._filename):
            raise RuntimeError("The stylefile does not exist: "+self._filename)
        self._filename = normalizePath(self._filename)
        self._styles = None
        self.loadStyles()    
    
    def loadStyles(self, filename=None):
        """ Load the stylefile. """
        
        # get filena,me
        if not filename:
            filename = self._filename
        else:
            self._filename = normalizePath(filename)
        
        # check file
        if not os.path.isfile(filename):
            filename = os.path.join( os.path.dirname(__file__), filename )
        if not os.path.isfile(filename):
            print("warning: style file not found.")
            return
        # load file
        import ssdf
        self._styles = ssdf.load(filename)
        self.buildStyleTree()
        self.styleUpdate.emit()
    
    def getStyleNames(self):
        return [name for name in self._styles]
    
    def buildStyleTree(self):
        """ Using the load ssdf file, build a tree such that
        the styles can be applied to the editors easily. """
        
        # a stylefile is an ssdf file which contains styling information
        # for several style types.
        # Each style is identified with a stylename and consists of a 
        # lexer, keywords, extension, several substyle strings (one for 
        # each substylenr) and can be based on any other style. 
        # All styles are automtically based on the style named default.
        
        if self._styles is None:
            return
        
        # do for each defined style
        for styleName in self._styles:
            
            # get style attributes
            style = self._styles[styleName]
            
            # make sure basedon and extensions are defined
            # keywords and lexer are only defined if they are in the file...     
            if not 'basedon' in style:
                style.basedon = ''
            if not 'ext' in style:
                style.ext = ''
            # dont do lexer or keywords, because they can be overridden to be
            # empty!
            
            # check out the substyle strings (which are of the form 'sxxx')
            for styleNr in style:
                if not (styleNr.startswith('s') and len(styleNr) == 4):
                    continue
                
                # get substyle number to tell scintilla
                nr = int(styleNr[1:])
                
                # Get string that contains several substyle attributes.
                # We will extract these attributes and organise them nicely
                # in a dict. 
                subStyleString = style[styleNr].lower()
                subStyleString = subStyleString.split(' # ')[0] # remove comments
                subStyleString = subStyleString.replace(',', ' ')
                subStyleString = subStyleString.replace(';', ' ')
                
                # split in parts
                subStyleStrings = subStyleString.split(' ')
                
                # store results in here
                subStyle = style[styleNr] = ssdf.new()
                
                # analyze
                for s in subStyleStrings:
                    if s.startswith('bold'):
                        subStyle['bold'] = 1
                    if s.startswith('italic'):
                        subStyle['italic'] = 1
                    if s.startswith('underline'):
                        subStyle['underline'] = 1
                    if s.startswith('fore:'):
                        tmp = s[len('fore:'):]
                        subStyle['fore'] = qt.QColor(tmp)
                    if s.startswith('back:'):
                        tmp = s[len('back:'):]
                        subStyle['back'] = qt.QColor(tmp)
                    if s.startswith('face:'):
                        tmp = s[len('face:'):]
                        subStyle['face'] = tmp.format(**FACES)
                    if s.startswith('size:'):
                        tmp = s[len('size:'):]
                        subStyle['size'] = int(tmp)
                #print(subStyle)
    
    
    def applyStyleNumber(self, editor, nr, subStyle):
        """ Apply a certain a numbered style to the given editor. """
        
        # special case first
        if nr > 255:
            
            def tryApplyColor(command, extraArg=None, key=None):
                if key in subStyle:
                    c = qt.QColor(subStyle[key])
                    if extraArg is not None:
                        editor.SendScintilla(command, extraArg, c)
                    else:
                        editor.SendScintilla(command, c)
            
            if nr == 301:  # highlighting current line
                tryApplyColor(editor.SCI_SETCARETFORE, None, 'fore')
                tryApplyColor(editor.SCI_SETCARETLINEBACK, None, 'back')
            elif nr == 302:  # selection colors...
                tryApplyColor(editor.SCI_SETSELFORE, 1, 'fore')
                tryApplyColor(editor.SCI_SETSELBACK, 1, 'back')
            elif nr == 303:  # calltip colors
                tryApplyColor(editor.SCI_CALLTIPSETFORE, None, 'fore')
                tryApplyColor(editor.SCI_CALLTIPSETBACK, None, 'back')
                tryApplyColor(editor.SCI_CALLTIPSETFOREHLT, None, 'forehlt')
        
        else:
        
            for key in subStyleStuff:
                scintillaCommand = subStyleStuff[key]
                if key in subStyle:
                    value = subStyle[key]
                    editor.SendScintilla(scintillaCommand, nr, value)
        
    
    def collectStyle(self, styleStruct, styleName):
        """ Collect the styleStruct, taking style inheritance
        into account. 
        """
        
        # get the style (but check if exists first)
        if not styleName in self._styles:
            print("Unknown style %s" % styleName)
            return
        style = self._styles[styleName]
        
        # First collect style on which it is based. 
        # A style is always based on default. 
        if style.basedon:
            self.collectStyle(styleStruct, style.basedon)
        elif styleName!='default':
            self.collectStyle(styleStruct, 'default')
        
        # collect all fields
        for field in style:
            styleStruct[field] = style[field]
    
    
    def applyStyle(self, editor, styleName):
        """ Apply the specified style to the specified editor. 
        The stylename can be the name of the style, or the extension
        of the file to be styled (indicated by starting with a dot '.')
        The actual stylename is returned.
        """
        
        # make lower case
        styleName = styleName.lower()
        if not styleName:
            styleName = 'default'
        
        # if styletree was not yet build, return
        if self._styles is None:
            return
        
        # if extension was given, find out which style it belongs to
        if styleName.startswith('.'):
            ext = styleName[1:]
            for styleName in self._styles:
                exts = self._styles[styleName].ext.split(' ')                
                if ext in exts:
                    break
            else:
                tmp = "Unknown extension {}, applying default style."
                print(tmp.format(ext))
                styleName = 'default'
        
        # get style struct
        styleStruct = ssdf.new()
        self.collectStyle(styleStruct, styleName)
        
        # clear all formatting
        editor.SendScintilla(editor.SCI_CLEARDOCUMENTSTYLE)
        
        if True: # apply always
            
            # short for sendscintilla
            send = editor.SendScintilla
            
            # First set default style to everything. The StyleClearAll command
            # makes that all styles are initialized as style 032. So it would
            # be more beautiful to look up that style and only apply that. But
            # it should always be defined in 'default', so this will work ...
            if 's032' in styleStruct:
                self.applyStyleNumber(editor, 32, styleStruct['s032'])
            send(editor.SCI_STYLECLEARALL)
            
            # set basic stuff first
            if 'lexer' in styleStruct:
                send(editor.SCI_SETLEXERLANGUAGE, styleStruct.lexer)
            if 'keywords' in styleStruct:
                send(editor.SCI_SETKEYWORDS, styleStruct.keywords)
            
            # check out the substyle strings (which are of the form 'sxxx')
            for styleNr in styleStruct:
                if not (styleNr.startswith('s') and len(styleNr) == 4):
                    continue
                # get substyle number to tell scintilla
                nr = int(styleNr[1:])
                # set substyle attributes
                self.applyStyleNumber(editor, nr, styleStruct[styleNr])
        
        # force scintilla to update the whole document
        editor.SendScintilla(editor.SCI_STARTSTYLING, 0, 32)
        
        # return actual stylename        
        return styleName

    
styleManager = StyleManager()
iep.styleManager = styleManager


class KeyEvent:
    """ A simple class for easier key events. """
    def __init__(self, key):
        self.key = key
        try:
            self.char = chr(key)        
        except ValueError:
            self.char = ""

    

def makeBytes(text):
    """ Make sure the argument is bytes, converting with UTF-8 encoding
    if it is a string. """
    if isinstance(text, bytes):
        return text
    elif isinstance(text, str):
        return text.encode('utf-8')
    else:
        raise ValueError("Expected str or bytes!")


class BaseTextCtrl(Qsci.QsciScintilla):
    """ The base text control class.
    Inherited by the shell class and the IEP editor.
    The class implements autocompletion, calltips, and auto-help,
    as well as styling and stuff like autoindentation.
    
    Inherits from QsciScintilla. I tried to clean up the rather dirty api
    by using more sensible names. Hereby I apply the following rules:
    - if you set something, the method starts with "set"
    - if you get something, the method starts with "get"
    - a position is the integer position fron the start of the document
    - a linenr is the number of a line, an index the position on that line
    - all the above indices apply to the bytes (encoded utf-8) in which the
      text is stored. If you have unicode text, they do not apply!
    - the method name mentions explicityly what you get. getBytes() returns the
      bytes of the document, getString() gets the unicode string that it 
      represents. This applies to the get-methods. the set-methods use the
      term text, and automatically convert to bytes using UTF-8 encoding
      when a string is given. 
    """
        
    def __init__(self, parent):
        Qsci.QsciScintillaBase.__init__(self,parent)
        
        # be notified of style updates
        self._styleName = ''
        styleManager.styleUpdate.connect(self.setStyle)
        
        # Create timer for autocompletion delay
        self._delayTimer = QtCore.QTimer(self)
        self._delayTimer.setSingleShot(True)
        self._delayTimer.timeout.connect(self.autoComplete_do_now)
        
        # For autocompletion
        self._autoComp_name = ''
        
        #print('Initializing Scintilla component.')
        
        # Do not use the QScintilla lexer
        self.setLexer()
        
        # SET PREFERENCES
        # Inherited classes may override some of these settings. Indentation
        # guides are not nice in shells for instance...
        
        self.setViewWhiteSpace(config.showWhiteSpace)
        self.setViewWrapSymbols(config.showWrapSymbols)
        self.setViewEOL(config.showLineEndings)
        
        self.setWrapMode( int(config.wrapText)*2 )
        self.setHighlightCurrentLine(config.highlightCurrentLine)
        self.zoomTo(config.zoom)
        self.setIndentationGuides(config.showIndentGuides)        
        
        self.setEdgeColumn(config.edgeColumn)
        self.setIndentation(config.defaultIndentation)
        self.setTabWidth(config.tabWidth)  
        
        self.setBraceMatching(int(config.doBraceMatch)*2)
        self.setFolding( int(config.codeFolding)*5 )
        
        # use unicode, the second line does not seem to do anything
        self.SendScintilla(self.SCI_SETCODEPAGE, self.SC_CP_UTF8)
        self.SendScintilla(self.SCI_SETKEYSUNICODE, 1) 
        # type of edge indicator        
        self.SendScintilla(self.SCI_SETEDGEMODE, self.EDGE_LINE)
        # tab stuff        
        self.SendScintilla(self.SCI_SETBACKSPACEUNINDENTS, True)
        self.SendScintilla(self.SCI_SETTABINDENTS, True)
        # line endings inside scintilla always \n
        self.setEolMode(self.SC_EOL_LF)
        self.SendScintilla(self.SCI_SETPASTECONVERTENDINGS, True)
        # line numbers in margin      
        self.SendScintilla(self.SCI_SETMARGINWIDTHN, 1, 30)
        self.SendScintilla(self.SCI_SETMARGINTYPEN, 1, self.SC_MARGIN_NUMBER)
        
        # HOME and END goto the start/end of the visible line, and also
        # for shift-home, shift end (selecting the text)
        if config.homeAndEndWorkOnDisplayedLine:
            shift,home,end = self.SCMOD_SHIFT<<16, self.SCK_HOME, self.SCK_END
            tmp1, tmp2 = self.SCI_HOMEDISPLAY, self.SCI_HOMEDISPLAYEXTEND
            self.SendScintilla(self.SCI_ASSIGNCMDKEY, home, tmp1)
            self.SendScintilla(self.SCI_ASSIGNCMDKEY, home+shift, tmp2)
            tmp1, tmp2 = self.SCI_LINEENDDISPLAY, self.SCI_LINEENDDISPLAYEXTEND
            self.SendScintilla(self.SCI_ASSIGNCMDKEY, end, tmp1)
            self.SendScintilla(self.SCI_ASSIGNCMDKEY, end+shift, tmp2)
        
        # Clear command keys that we make accesable via menu shortcuts.
        # Do not clear all command keys; 
        # that even removes the arrow keys and such.
        ctrl, shift = self.SCMOD_CTRL<<16, self.SCMOD_SHIFT<<16
        # these we all map via the edit menu
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('X')+ ctrl)
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('C')+ ctrl)
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('V')+ ctrl)
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('Z')+ ctrl)
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('Y')+ ctrl)
        self.SendScintilla(self.SCI_CLEARCMDKEY, ord('A')+ ctrl)
#         # these are mostly not used ... but we might just leave them ...
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('D')+ ctrl)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('L')+ ctrl)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('L')+ ctrl+shift)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('T')+ ctrl)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('T')+ ctrl+shift)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('U')+ ctrl)
#         self.SendScintilla(self.SCI_CLEARCMDKEY, ord('U')+ ctrl+shift)
        
        # calltips, I dont know what this exactly does
        #self.setCallTipsStyle(self.CallTipsNoContext)
        
        # Autocompletion settings

        # Typing one of these characters will SCI_AUTOCCANCEL
        stopChars = ' .,;:([)]}\'"\\<>%^&+-=*/|`'
        self.SendScintilla(self.SCI_AUTOCSTOPS, None, stopChars)
        
        # This char is used to seperate the words given with SCI_AUTOCSHOW
        self.SendScintilla(self.SCI_AUTOCSETSEPARATOR, 32) # space
        
        # If True SCI_AUTOCCANCEL when the caret moves before the start pos 
        self.SendScintilla(self.SCI_AUTOCSETCANCELATSTART, False)
        
        # These characters will SCI_AUTOCCOMPLETE automatically when typed
        # I prefer not to have fillups.
        self.SendScintilla(self.SCI_AUTOCSETFILLUPS, '')
        
        # If True, will SCI_AUTOCCOMPLETE when list has only one item
        self.SendScintilla(self.SCI_AUTOCSETCHOOSESINGLE, False)
        
        # If True, will hide the list if no match. Set to True, although
        # we will also do the check ourselves 
        self.SendScintilla(self.SCI_AUTOCSETAUTOHIDE, True)
        
        # Set case sensitifity - case insensitivity is so very handy
        self.SendScintilla(self.SCI_AUTOCSETIGNORECASE, True)
        
        # If True, will erase the word-chars following the caret 
        # before inserting selected text. Please don't!
        self.SendScintilla(self.SCI_AUTOCSETDROPRESTOFWORD, False)
        
        # Amount of items to display in the list. Amount of chars set auto.
        # The first does not seem to have any effect.
        self.SendScintilla(self.SCI_AUTOCSETMAXHEIGHT, 10)
        self.SendScintilla(self.SCI_AUTOCSETMAXWIDTH, 0)
    
    
    def SendScintilla(self, *args):
        """ Overloaded method that transforms any string arguments to
        bytes arguments. 
        This is required in PyQt4 4.6.2, but not in earlier versions.
        """
        # copy args, transforming strings to bytes
        args2 = []
        for arg in args:
            if isinstance(arg, (bytes, str)):
                args2.append( makeBytes(arg) )
            else:
                args2.append( arg )
        # send it
        args = tuple( args2 )
        return Qsci.QsciScintillaBase.SendScintilla(self, *args)
    
    
    ## getting and setting text
    
    
    def getBytesLength(self):
        """ Get the length of the (encoded) text. 
        .length() does the same)
        """
        return self.length()
    
    
    def setText(self, value):
        """ Set the text of the editor. """
        self.SendScintilla(self.SCI_SETTEXT, makeBytes(value))
    
    def getBytes(self):
        """ Get the text as bytes (utf-8 encoded). This is how
        the data is stored internally. """
        # +1 because Null character needs to fit in too
        len = self.SendScintilla(self.SCI_GETLENGTH)+1
        bb = QtCore.QByteArray(len,'0')
        N = self.SendScintilla(self.SCI_GETTEXT, len, bb)
        return bytes(bb)[:-1] # remove NULL character
    
    def getString(self):
        """ Get the text as a unicode string. """
        return self.getBytes().decode('utf-8')
    
    
    def getLineBytes(self, linenr):
        """ Get the bytes of the given line. """
        # +1 because Null character needs to fit in too
        len = self.SendScintilla(self.SCI_LINELENGTH, linenr)+1
        bb = QtCore.QByteArray(len,'0')
        N = self.SendScintilla(self.SCI_GETLINE, linenr, bb)
        return bytes(bb)[:-1] # remove NULL character
    
    def getLineString(self, linenr):
        """ Get the string of the given line. """
        return self.getLineBytes(linenr).decode('utf-8')
        
    
    def getSelectedBytes(self):
        """ Get the bytes that are currently selected. """
        # +1 because Null character needs to fit in too
        len = self.SendScintilla(self.SCI_GETSELTEXT, 0, 0) # not +1
        bb = QtCore.QByteArray(len,'0')
        N = self.SendScintilla(self.SCI_GETSELTEXT, 0, bb)
        return bytes(bb)[:-1] # remove NULL character
    
    def getSelectedString(self):
        """ Get the string that represents the currently selected text. """
        return self.getSelectedBytes().decode('utf-8')
    
    def replaceSelection(self, replacement):
        """ Replace the selected text with the given bytes or string. """
        self.SendScintilla(self.SCI_REPLACESEL, 0, replacement)
    
    def getRangeBytes(self, pos1, pos2):
        """ Get the bytes from pos1 up til pos2 (non inclusive). """
        # There's a sendscintilla command for this, but it involves
        # a struct, so I am afraid it is not possible to use that.
        bb = self.getBytes()
        return bb[pos1:pos2]
    
    def getRangeString(self, pos1, pos2):
        """ Get the string from pos1 up til pos2 (non inclusive). """
        return self.getRangeBytes(pos1, pos2).decode('utf-8')
    
    
    def getStyleAt(self, pos):
        """ Get the style at the given position."""
        return self.SendScintilla(self.SCI_GETSTYLEAT,pos)
    
    def getCharAt(self,pos):
        """ Get the character at the current position. """
        char = self.SendScintilla(self.SCI_GETCHARAT, pos)
        if char == 0:
            return ""
        elif char < 0:
            return chr(char + 256)
        else:
            return chr(char)
    
    
    def appendText(self, value):
        """ insert the given text at the given position. """
        value = makeBytes(value)
        self.SendScintilla(self.SCI_APPENDTEXT, len(value), value)
    
    def insertText(self, pos, value):
        """ insert the given text at the given position. """
        self.SendScintilla(self.SCI_INSERTTEXT, pos, makeBytes(value))
    
    def addText(self, value):
        """ insert text at the current position. """
        value = makeBytes(value)
        self.SendScintilla(self.SCI_ADDTEXT, len(value), value)
    
    ## Positional methods
    
    def setPosition(self, pos):
        """ Set the position of the cursor. """
        self.SendScintilla(self.SCI_SETCURRENTPOS, pos)
    
    def setAnchor(self, pos):
        """ Set the position of the anchor. """
        self.SendScintilla(self.SCI_SETANCHOR, pos)
    
    def setPositionAndAnchor(self, pos):
        """ Set both position and anchor to the same position. """
        self.SendScintilla(self.SCI_SETCURRENTPOS, pos)
        self.SendScintilla(self.SCI_SETANCHOR, pos)
    
    def getPosition(self):
        """ Get the current position of the cursor. """
        return self.SendScintilla(self.SCI_GETCURRENTPOS)
    
    def getAnchor(self):
        """ Get the anchor (as int) of the cursor. If this is
        different than the position, text is selected."""
        return self.SendScintilla(self.SCI_GETANCHOR)
    
    
    def getLinenrAndIndex(self, pos=None):
        """ Get the linenr and index of the given position,
        or the current position if pos is None. """
        if pos is None:
            pos = self.SendScintilla(self.SCI_GETCURRENTPOS)
        linenr = self.SendScintilla(self.SCI_LINEFROMPOSITION, pos)
        index = pos - self.SendScintilla(self.SCI_POSITIONFROMLINE, linenr)
        return linenr, index
    
    def getLinenrFromPosition(self, pos=None):
        """ Get the linenr, given the position (or the
        current position if pos is None). """
        if pos is None:
            pos = self.SendScintilla(self.SCI_GETCURRENTPOS)
        return self.SendScintilla(self.SCI_LINEFROMPOSITION, pos)
    
    def getPositionFromLinenr(self, linenr):
        """ Get the position, given the line number. """
        return self.SendScintilla(self.SCI_POSITIONFROMLINE , linenr)
    
    def setTargetStart(self, pos):
        """ Set the start of selection target. 
        The target is used in various task and can be seen
        as a selection that is not shown to the user. """
        self.SendScintilla(self.SCI_SETTARGETSTART, pos)
    
    def setTargetEnd(self, pos):
        """ Set the end of selection target. 
        The target is used in various task and can be seen
        as a selection that is not shown to the user. """
        self.SendScintilla(self.SCI_SETTARGETEND, pos)
    
    def replaceTargetBytes(self, value):
        """ replace the target with the selected bytes. 
        The target is used in various task and can be seen
        as a selection that is not shown to the user. """        
        self.SendScintilla(self.SCI_REPLACETARGET, len(value), value)
    
    def replaceTargetString(self, value):
        """ replace the target with the selected string. 
        The target is used in various task and can be seen
        as a selection that is not shown to the user. """        
        value = value.encode('utf-8')
        self.SendScintilla(self.SCI_REPLACETARGET, len(value), value)
    
    
    ## Settings methods
    
    def setIndentation(self, value):
        """ Set the used indentation. If a number larger than 0,
        tabs are disabled and the number is the amount of spaces for
        an indent. If the number is negative, tabs are used for 
        indentation. """
        if value < 0:
            self.SendScintilla(self.SCI_SETUSETABS, True)
            self.SendScintilla(self.SCI_SETINDENT, 0)
        else:
            self.SendScintilla(self.SCI_SETUSETABS, False)
            self.SendScintilla(self.SCI_SETINDENT, value)
    
    def getIndentation(self):
        """ Get the used indentation. See setIndentation for details. """
        if self.SendScintilla(self.SCI_GETUSETABS):
            return -1
        else:
            return self.SendScintilla(self.SCI_GETINDENT)
    
    
    def setTabWidth(self, width):
        """ Set the tab width. """
        self.SendScintilla(self.SCI_SETTABWIDTH, width)    
    
    def getTabWidth(self):
        """ Get the tab width. """
        return self.SendScintilla(self.SCI_GETTABWIDTH)
    
    
    def setViewWhiteSpace(self, value):
        """ Set the white space visibility, can be True or False, 
        or 0, 1, or 2, where 2 means show after indentation. """
        value = int(value)
        self.SendScintilla(self.SCI_SETVIEWWS, value)
    
    def getViewWhiteSpace(self):
        """ Get the white space visibility, can be 0, 1 or 2, 
        where 2 means show after indentation. """
        return self.SendScintilla(self.SCI_GETVIEWWS)
    
    def setViewEOL(self, value):
        """ Set the line ending visibility, can be True or False. """
        value = int(value)
        self.SendScintilla(self.SCI_SETVIEWEOL, value)
    
    def getViewEOL(self):
        """ Get the line ending visibility. """
        return self.SendScintilla(self.SCI_GETVIEWEOL)
    
    def setViewWrapSymbols(self, value):
        """ Set the wrap symbols visibility, can be True or False,
        or 0,1 or 2, for off, show-at-end, show-at-start, respectively. """
        value = int(value)
        self.SendScintilla(self.SCI_SETWRAPVISUALFLAGS, value)
    
    def getViewWrapSymbols(self):
        """ Get the wrap symbols visibility. Is 0,1 or 2, 
        for off, show-at-end, show-at-start, respectively. """
        return self.SendScintilla(self.SCI_GETWRAPVISUALFLAGS)
        
    def setHighlightCurrentLine(self, value):
        """ Set whether or not to highlight the line containing the caret.
        Call SCI_SETCARETLINEBACK(int color) to set the color
        """
        self.SendScintilla(self.SCI_SETCARETLINEVISIBLE, bool(value))
    
    def getHighlightCurrentLine(self):
        """ Get whether or not to highlight the line containing the caret.
        Call SCI_SETCARETLINEBACK(int color) to set the color
        """
        return self.SendScintilla(self.SCI_GETCARETLINEVISIBLE)
    
#     def setWrapMode(self, value):
#         """ Set the wrapmode of the editor. 
#         0: no wrap, 1: wrap word, 2: wrap character.
#         1 is not recommended since it is very slow. """
#         self.SendScintilla(self.SCI_SETWRAPMODE, value)
#     
#     def getWrapMode(self, value):
#         """ Get the wrapmode of the editor. 
#         0: no wrap, 1: wrap word, 2: wrap character.
#         1 is not recommended since it is very slow. """
#         return self.SendScintilla(self.SCI_GETWRAPMODE)
#     
#     
#     def setEdgeColumn(self, value):
#         """ Set the position of the edge column of the editor. """
#         self.SendScintilla(self.SCI_SETEDGECOLUMN, value)
#     
#     def getEdgeColumn(self):
#         """ Get the position of the edge column of the editor. """
#         return self.SendScintilla(self.SCI_GETEDGECOLUMN)
#     
#     
#     def setIndentationGuides(self, value):
#         """ Set whether or not to show indentation guides. """
#         self.SendScintilla(self.SCI_SETINDENTATIONGUIDES, value)
#     
#     def getIndentationGuides(self):
#         """ Get whether or not to show indentation guides."""
#         return self.SendScintilla(self.SCI_GETINDENTATIONGUIDES)
#     
#     
#     def setEolMode(self, value):
#         """ Set The line ending mode to apply. """
#         self.SendScintilla(self.SCI_SETEOLMODE, value)
#     
#     def getEolMode(self):
#         """ Get The line ending mode to apply. """
#         return self.SendScintilla(self.SCI_GETEOLMODE)
    
    
    def setStyle(self, styleName=None):
        """ Set the styling used, or the extension of the file. """
        # remember style or use remebered style
        if styleName is None:
            styleName = self._styleName        
        # apply and remember
        self._styleName = styleManager.applyStyle(self,styleName)
    
    def getStyleName(self):
        """ Get the name of the currently applied style. """
        return self._styleName
    
    def textWidth(self, style=32, value='X'):
        """ Get the width (in pixels) of the given text. """
        return self.SendScintilla(self.SCI_TEXTWIDTH, style, value)
    
    
    ## Autocompletion and other introspection methods
    
    
#     # the method below is not used because Qscintilla has it build in
#     def doBraceMatch(self,event=None):
#         """ Match braces and highlight accordingly.
#         Called on EVT_STC_UPDATEUI.        
#         """
#        
#         if not config.doBraceMatch:
#             return
#         
#         # get location of current brace and the match
#         i1 = self.getCurrentPos()        
#         
#         # get char at the cursor        
#         chara, charb = 'a', 'b'
#         if i1>0 and i1 < self.length():
#             chara = self.getCharAt(i1-1)
#             charb = self.getCharAt(i1)
#         
#         # do we have a brace right before or after the cursor?
#         if charb in '()[]{}':
#             i1 = i1
#         elif chara in '()[]{}':
#             i1 = i1-1
#         else:
#             self.SendScintilla(self.SCI_BRACEBADLIGHT, -1)
#             return
#         
#         # match brace
#         i2 = self.SendScintilla(self.SCI_BRACEMATCH, i1) 
#         if i2<0:
#             self.SendScintilla(self.SCI_BRACEBADLIGHT,i1)
#         else:        
#             self.SendScintilla(self.SCI_BRACEHIGHLIGHT, i1, i2)
    
    
    """ Help on some autocomp functions
        SCI_AUTOCSHOW # Start showing list
        SCI_AUTOCCANCEL # Hide list, do nothing
        SCI_AUTOCACTIVE # query whether is active
        SCI_AUTOCPOSSTART # value of the current position when SCI_AUTOCSHOW
        SCI_AUTOCCOMPLETE # Finish: insert selected text
        
        SCI_AUTOCSELECT # Programatically Select an item in the list
        SCI_AUTOCGETCURRENT # Get current selection index
        SCI_AUTOCGETCURRENTTEXT # Currently selected text
        """
    
    def autoCompShow(self, lenentered, names): 
        """ Start showing the autocompletion list, 
        with the list of given names (which can be a list or a space separated
        string.
        """
        if isinstance(names, list):
            names = ' '.join(names)  # See SCI_AUTOCSETSEPARATOR
        self.SendScintilla(self.SCI_AUTOCSHOW, lenentered, names)
    
    
    def autoCompCancel(self):
        """ Hide the autocompletion list, do nothin. """
        self.SendScintilla(self.SCI_AUTOCCANCEL)
    
    
    def autoCompActive(self):  
        """ Get whether the autocompletion is currently active. """
        return self.SendScintilla(self.SCI_AUTOCACTIVE)
    
    
    def autoCompComplete(self):
        """ Perform autocomplete: 
        insert the selected item and hide the list. """
        self.SendScintilla(self.SCI_AUTOCCOMPLETE)
    
    
    def _isValidPython(self):
        """ Check if the code at the cursor is valid python:
        - the active lexer is the python lexer
        - the style at the cursor is "default"
        """
        
        # The lexer should be Python
        lexlang = self.SendScintilla(self.SCI_GETLEXER)
        if lexlang != self.SCLEX_PYTHON:
            return False
        
#         # The style must be "default"
#         curstyle = self.getStyleAt(self.getPosition())
#         if curstyle not in [32,10]:
#             return False
        
        # all good
        return True  
    
    
    def autoComplete_do(self):
        """ Perform autocompletion
        This method is called after a char is entered or backspace is used.
        Parses the line and finds the baseobject and the needle part: the
        part that needs completing.
        
        It is verified that the autocompletion box should be shown. If 
        so, a timer is started that will call autocomplete_do_now() in
        xx seconds.
        
        This method calls _Autocomplete_do which makes sure that the 
        analysis is only done if no keys have been pressed for 100ms.
        The analysis consists of checking whether the needle is in 
        the list and if so, select that item in the STC automcompletion 
        list. If not, hide the popup list.
        The list is queried by _Autocomplete_produceList, which may query
        the list from the active session or use a previously queried 
        list.
        """
        
#         # only proceed if we're supposed to
#         if not iep.config.doAutoComplete:
#             self.StopIntrospecting()
#             return
        
        # only proceed if valid python
        if not self._isValidPython():
            self.autoCompCancel()
            return
        
        # Get line up to cursor
        linenr, i = self.getLinenrAndIndex()
        text = self.getLineString(linenr)
        text = text[:i]
        
        # is the char valid?        
        if not text or not ( text[-1] in namechars or text[-1]=='.' ):
            self.autoCompCancel()
            return
        
        # Store line and (re)start timer
        self._delayTimer._line = text
        self._delayTimer.start(iep.config.autoCompDelay)
    
    
    def autoComplete_do_now(self):
        # todo: better names for methods
        
        # Parse the line, to see what (partial) name we need to complete
        line = self._delayTimer._line
        if not line:
            return
        baseObject, name = parseLine_autocomplete(line)
        name = name.lower()
        
        # Store name to search for
        self._autoComp_name = baseObject + '.' + name
        
        # Process by posting a request at the shell
        if name or baseObject:
            req = "DIR " + baseObject
            shell = iep.shells.getCurrentShell()
            shell.postRequest(req, self.autoComplete_process)
    
    
    def autoComplete_process(self, response):
        
        # todo: also send and receive back the self._autoComp_name so
        # we can determine whether it's still up-to-date
        
        # Should we process at all?
        if not self._autoComp_name:
            self.autoCompCancel()
            return
        
        # Get baseObject, name
        baseObject, name = self._autoComp_name.split('.')
        
        # Make list
        response = response.split(',')
        
        # First see if this is still the right editor (can also be a shell)
        editor1 = iep.editors.getCurrentEditor()
        editor2 = iep.shells.getCurrentShell()
        if editor1 is not self and editor2 is not self:
            # This editor is no longer active
            self.autoCompCancel()
            return
        
        # Insert  builtins
        if editor2 and not baseObject:
            response.extend(editor2._builtins)
        
        # Sort the response
        response.sort(key=str.upper)
        
        # Check whether name in list. We do it like this rather than
        # using AutoCompAutoHide() because it prevents flicker.    
        thename = ""
        for item in response:
            if item.lower().startswith(name):
                thename = item
                break
        # if not, hide
        if not thename:
            self.autoCompCancel()
        else:
            # Show completion list if required. 
            # When already shown the list will change selection when typing
            if not self.autoCompActive():
                self.autoCompShow(len(name), response)
    
    ## Callbacks
    
    
    def keyPressEvent(self, event):
        """ Receive qt key event. 
        From here we'l dispatch the event to perform autocompletion
        or other stuff...
        """
        # todo: Each autocomplete request should get an id or so,
        # such that when the autocomplete wants to show the result,
        # it can deside not to when the user has for example already
        # pressed enter.
        
        # Create simple keyevent class and set modifiers
        keyevent = KeyEvent( event.key() )
        modifiers = event.modifiers()
        keyevent.controldown = modifiers & QtCore.Qt.ControlModifier
        keyevent.altdown = modifiers & QtCore.Qt.AltModifier
        keyevent.shiftdown = modifiers & QtCore.Qt.ShiftModifier
        
        # Cancel any autocompletion in progress
        # todo: can we not use a single flag for this?
        self._delayTimer._line = ''
        self._autoComp_name = ''
        
        # Dispatch event        
        if not self.keyPressHandler_always(keyevent):
            handled = False
            if self.autoCompActive():
                handled = self.keyPressHandler_autoComp(keyevent)
            else:
                # Handle normal key event
                handled = self.keyPressHandler_normal(keyevent)
            
            # Should we handle it the normal way?
            if not handled:
                Qsci.QsciScintillaBase.keyPressEvent(self, event)
        
        # Process character press
        if event.text():
            key = ord( event.text() )
            if key >= 48 or key == 8:
                # If a char that allows completion or backspace was pressed
                self.autoComplete_do()
    
    
    def keyPressHandler_always(self, event):
        """ keyPressHandler_always(event)
        Is always called. If returns True, will not proceed.
        If return False or None, keyPressHandler_autoComp or 
        keyPressHandler_normal is called, depending on whether the
        autocompletion list is active.
        """
        pass
    
    
    def keyPressHandler_autoComp(self, event):
        """ keyPressHandler_autoComp(event)
        Called when the autocomp list is active and when the event
        was not handled by the "always" handler. If returns True,
        will not process the event further.
        """
        pass 
        # todo: show interactive help when moving up/down
#         updown = [QtCore.Qt.Key_Up, QtCore.Qt.Key_Down]
#         if event.key in updown and self.autoCompActive():
#             # show help!
#             return False

#             # get current selected name in autocomp list
#             try:                
#                 i = self.AutoCompGetCurrent()
#                 i += {wx.WXK_UP:-1, wx.WXK_DOWN:+1}[key]
#                 if i< 0: 
#                     i=0
#                 if i>=len(self._introspect_list):
#                     i = len(self._introspect_list) -1 
#                 name = self._introspect_list[ i ]
#             except IndexError:
#                 name = ""
#             # add base part
#             if self._introspect_baseObject:
#                 name = self._introspect_baseObject + "." + name
#             
#             # aply
#             self.Introspect_help(name,True)

    
    def keyPressHandler_normal(self, event):
        """ keyPressHandler_normal(event)
        Called when the autocomp list is NOT active and when the event
        was not handled by the "always" handler. If returns True,
        will not process the event further.
        """
        return False
        
        
#         if event.key == QtCore.Qt.Key_Escape:
#             # clear signature of current object 
#             self._introspect_signature = ("","")
        
#         if event.key == QtCore.Qt.Key_Backspace:
#             doAutocomplete(self, '', '')
#             #wx.CallAfter(self.Introspect_autoComplete)
#             #wx.CallAfter(self.Introspect_signature)
            
#         if event.key in [QtCore.Qt.Key_Left, QtCore.Qt.Key_Right]:
#             # show signature also when moving inside it
#             pass
#             #wx.CallAfter(self.Introspect_signature)


if __name__=="__main__":
    app = QtGui.QApplication([])
    win = BaseTextCtrl(None)
    win.setStyle('.py')
    tmp = "foo(bar)\nfor bar in range(5):\n  print bar\n"
    tmp += "\nclass aap:\n  def monkey(self):\n    pass\n\n"
    tmp += "a\u20acb\n"
    win.setText(tmp)    
    win.show()
    styleManager.loadStyles() # this is not required (but do now for testing)
    app.exec_()
    
