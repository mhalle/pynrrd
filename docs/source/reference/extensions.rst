.. _extensions:

=======================================================
Extensions
=======================================================

.. currentmodule:: nrrd.extensions

The extensions module provides support for storing structured metadata in NRRD files
using a JSON-based format while maintaining backward compatibility.

Functions
=======================================================

.. autofunction:: process_extension_fields
.. autofunction:: prepare_extensions_for_writing

Extension Data Structure
=======================================================

When using the NRRD extensions mechanism, users should provide two special fields
in the header:

1. **extensions**: A dictionary mapping extension names to URI strings.
   
   Example::
   
       'extensions': {
           'meta': 'https://example.org/meta',
           'dicom': 'https://example.org/dicom'
       }

2. **extension_data**: A dictionary containing extension data organized by extension name.
   
   Example::
   
       'extension_data': {
           'meta': {
               'author': 'Jane Doe',
               'date': '2023-01-01',
               'version': 1.0
           },
           'dicom': {
               'patientID': '12345',
               'studyDate': '20230101'
           }
       }

Extension Field Serialization
=======================================================

When writing NRRD files, extension data is automatically flattened and serialized
to JSON format. When reading NRRD files with extensions, the flattened extension
fields are reconstructed into a hierarchical structure.

For example, an extension with hierarchical data like this::

    'extension_data': {
        'analysis': {
            'segmentation': {
                'method': 'automatic',
                'regions': [
                    {'id': 1, 'name': 'tumor'},
                    {'id': 2, 'name': 'edema'}
                ]
            }
        }
    }

Will be flattened and written to the NRRD file as::

    analysis/segmentation.method:="automatic"
    analysis/segmentation.regions[0].id:=1
    analysis/segmentation.regions[0].name:="tumor"
    analysis/segmentation.regions[1].id:=2
    analysis/segmentation.regions[1].name:="edema"

Low-Level Functions
=======================================================

The following functions implement the core extensions functionality and
are typically used internally by the higher-level functions:

.. autofunction:: parse_extensions_from_header
.. autofunction:: find_extension_keys
.. autofunction:: parse_json_value
.. autofunction:: serialize_nrrd_json
.. autofunction:: get_field_type_extension