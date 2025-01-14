from distutils.core import setup
from distutils.command.build_py import build_py as _build_py
import subprocess
import os
import logging
log=logging.getLogger("setup_py")
logging.basicConfig(level=logging.INFO)
log.info("Now building")
try: #If we are in a git-repo, get git-describe version.
    path = os.path.abspath(os.path.dirname(__file__))
    ernwin_version = subprocess.check_output(["git", "describe", "--always"]).strip()
    log.info("Ernwin version read: %s", ernwin_version)
    try:
        subprocess.check_call(["git", 'diff-index', '--quiet', 'HEAD', '--'])

    except subprocess.CalledProcessError:
        ernwin_version+="+uncommited_changes"
    #Use a subclass of build_py from distutils to costumize the build.
    class build_py(_build_py):
        def run(self):
            """
            During building, adds a variable with the complete version (from git describe)
            to fess/__init__.py.
            """
            try:
                outfile = self.get_module_outfile(self.build_lib, ["fess"], "__init__")
                os.remove(outfile) #If we have an old version, delete it, so _build_py will copy the original version into the build directory.
            except:
                log.exception("")
                pass
            # Superclass build
            print("Running _build_py")
            _build_py.run(self)
            print("Postprocessing")
            outfile = self.get_module_outfile(self.build_lib, ["fess"], "__init__")
            # Apped the version number to init.py
            with open(outfile, "a") as of:
                log.info("ernwin_version %s", ernwin_version)
                of.write('\n__complete_version__ = "{}"'.format(ernwin_version))
except OSError: #Outside of a git repo, do nothing.
    log.exception("Not in a git repo")
    build_py = _build_py




setup(cmdclass={'build_py': build_py},
      name='ernwin',
      version='1.0.1',
      description='Coarse Grain 3D RNA Structure Modelling',
      author='Bernhard Thiel, Peter Kerpedjiev',
      author_email='thiel@tbi.univie.ac.at, pkerp@tbi.univie.ac.at',
      url='http://www.tbi.univie.ac.at/~thiel/ernwin/',
      packages = ['fess', 'fess.builder', 'fess.ccd', 'fess.motif'],
      install_requires = [
         "pandas>=0.19",
         "numpy",
         "scipy",
         "biopython",
         "deepdiff<3.3.1",
         "networkx",
         "future",
         "forgi>=2.1.2",
         "logging_exceptions",
         "commandline_parsable",
         "scikit-learn",
         "matplotlib",
         "contextlib2"
      ],
      package_data={'fess': ['stats/all_nr3.36.stats',
                             'stats/cylinder_intersections*.csv',
                             'stats/cde_reference_dist_nr2.110.csv',
                             'stats/sld_reference_dist_nr2.110.csv',
                             'stats/rog_reference_dist_nr2.110.csv',
                             'stats/rog_target_dist_nr2.110.csv',
                             'stats/sld_target_dist_nr2.110.csv',
                             'stats/sld_reference_dist_1S72_0.csv',
                             'stats/rog_reference_dist_1S72_0.csv',
                             'stats/rog_target_dist_1S72_0.csv',
                             'stats/sld_target_dist_1S72_0.csv',
                             'stats/residue_template.pdb',
                             'stats/AME_distributions.csv']},
      scripts=['fess/scripts/ernwin.py', 'fess/scripts/reconstruct.py', 'fess/scripts/plot_ernwin_pdd.py']
     )
