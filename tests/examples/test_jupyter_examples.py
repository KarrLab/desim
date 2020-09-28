""" Test Jupyter notebooks

:Author: Jonathan Karr <karr@mssm.edu>
:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2020-06-27
:Copyright: 2020, Karr Lab
:License: MIT
"""

import glob
import itertools
import json
import nbconvert.preprocessors
import nbformat
import os
import unittest


@unittest.skipIf(os.getenv('CIRCLECI', '0') in ['1', 'true'], 'Jupyter server not setup in CircleCI')
class ExamplesTestCase(unittest.TestCase):
    TIMEOUT = 300

    def test_jupyter(self):
        print()
        failed_notebooks = []
        for filename in itertools.chain(glob.glob('de_sim/examples/jupyter_examples/*.ipynb'),
                                        glob.glob('de_sim/examples/jupyter_examples_for_talk/*.ipynb')):
            print('filename:', filename)
            with open(filename) as file:
                version = json.load(file)['nbformat']
            with open(filename) as file:
                notebook = nbformat.read(file, as_version=version)
            execute_preprocessor = nbconvert.preprocessors.ExecutePreprocessor(timeout=self.TIMEOUT)
            try:            
                execute_preprocessor.preprocess(notebook, {'metadata': {'path': os.path.dirname(filename)}})
            except Exception as e:
                failed_notebooks.append(f"Notebook {filename} failed with error '{e}'")
            print('failed_notebooks', failed_notebooks)

        if failed_notebooks:
            e_message = '\n  '.join(sorted(failed_notebooks))
            failure = f'The following notebooks could not be executed:\n {e_message}'
            self.fail(failure)
