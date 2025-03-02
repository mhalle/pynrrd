from typing import Any, Dict

from typing_extensions import Literal

NRRDFieldType = Literal['int', 'double', 'string', 'int list', 'double list', 'string list', 'quoted string list',
                        'int vector', 'double vector', 'int matrix', 'double matrix', 'int vector list',
                        'double vector list', 'json']

IndexOrder = Literal['F', 'C']

NRRDFieldMap = Dict[str, NRRDFieldType]
NRRDHeader = Dict[str, Any]

# Extension-related type definitions
ExtensionName = str
ExtensionURI = str
ExtensionRegistry = Dict[ExtensionName, ExtensionURI]
ExtensionData = Dict[str, Any]
