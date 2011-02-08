import sys

# Set Python version as a float and get some names
PYTHON_VERSION = sys.version_info[0] + sys.version_info[1]/10.0
if PYTHON_VERSION < 3:
    ustr = unicode
    bstr = str
else:
    ustr = str
    bstr = bytes



DEFAULT_OPTION_NAME = '_ce_default_value'
DEFAULT_OPTION_NONE = '_+_just some absurd value_+_'

def ce_option(arg1):
    """ Decorator for properties of the code editor. 
    
    It should be used on the setter function, with its default value
    as an argument. The default value is then  stored on the function
    object. 
    
    At the end of the initialization, the base codeeditor class will 
    check all members and (by using the default-value-attribute as a
    flag) select the ones that are options. These are then set to
    their default values.
    
    Similarly this information is used by the setOptions method to
    know which members are "options".
    
    """ 
    
    # If the decorator is used without arguments, arg1 is the function
    # being decorated. If arguments are used, arg1 is the argument, and
    # we should return a callable that is then used as a decorator.
    
    # Create decorator function.
    def decorator_fun(f):
        f.__dict__[DEFAULT_OPTION_NAME] = default
        return f
    
    # Handle
    default = DEFAULT_OPTION_NONE
    if hasattr(arg1, '__call__'):
        return decorator_fun(arg1)
    else:
        default = arg1
        return decorator_fun
    
    