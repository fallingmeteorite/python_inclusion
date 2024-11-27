import argparse
import logging as log_use
import os
import shutil
import sys

import chardet
import colorlog


def get_logger(level=log_use.INFO):
    # Create a logger object
    logger = log_use.getLogger()
    logger.setLevel(level)
    # Create a console log processor
    console_handler = log_use.StreamHandler()
    console_handler.setLevel(level)
    # Define the color output format
    color_formatter = colorlog.ColoredFormatter(
        '%(log_color)s | %(asctime)s | %(levelname)s : %(message)s',
        log_colors={
            'DEBUG': 'blue,bg_white',
            'INFO': 'green,bg_white',
            'WARNING': 'yellow,bg_white',
            'ERROR': 'red,bg_white',
            'CRITICAL': 'red,bg_yellow',
        }
    )
    # Add the color output format to the console log processor
    console_handler.setFormatter(color_formatter)
    # Remove the default handler
    for handler in logger.handlers:
        logger.removeHandler(handler)
    # Add the console log handler to the logger object
    logger.addHandler(console_handler)
    return logger


def remove_element_and_next(target):
    global args
    global requirements_list
    # Locate the index of all target elements
    indices = [i for i, x in enumerate(args) if x == target]

    # Remove elements and their next bits from back to front to avoid the impact of index changes
    for i in reversed(indices):
        if i + 1 < len(args):  # 确保有后一位
            requirements_list.append(args[i + 1])
            args.pop(i + 1)
        else:
            requirements_list.append(None)
        args.pop(i)


def run(parameter_import, rules_open, delete_cache, parent_path, run_check=True):
    global requirements_list

    # Enable rule detection
    if rules_open:

        # Open the txt file, read each row of data and store it in the data array
        with open(f'{parent_path}\\Inclusion_rules_package.txt', 'r', encoding='utf-8') as file:
            lines = file.readlines()

        for i in range(len(lines)):
            package_check = str(lines[i])
            package_check = package_check.replace(' ', '')

            # Check whether there are any blacklisted packages in the command
            if package_check in str(parameter_import):
                # Check whether it is an installation command
                if 'install' in parameter_import:
                    logging.warning(
                        f'The current command is detected to be making changes to the |{package_check}| library, and the current command will be intercepted!')
                    logging.warning(
                        'If you confirm that the change is necessary, add the parameter |-rules_open| and set it to |off|')

                    # Prohibit the execution of installation commands
                    run_check = False

        # Detect whether there are any blacklisted packages in the requirements.txt
        if len(requirements_list) > 1:
            for h in range(len(requirements_list)):
                requirements = requirements_list[h]

                if len(lines) == 0:
                    parameter_import += f' -r {requirements}'

                for k in range(len(lines)):
                    package_check = str(lines[k])
                    package_check = package_check.replace(' ', '')

                    logging.info(
                        'The current command is detected to be installing dependent files in batches, and requirements.txt files are being detected')
                    logging.info(f'{requirements} detects the file path')

                    # Read each row of data and store it in the data array
                    # Detect file encoding
                    with open(requirements, 'rb') as f:
                        raw_data = f.read()
                        result = chardet.detect(raw_data)
                        encoding = result['encoding']

                    with open(requirements, 'r', encoding=encoding) as file:
                        lines = file.readlines()

                        for l in range(len(lines)):
                            if package_check == lines[l]:
                                lines[l] = ''
                                logging.warning(
                                    f'The current command is detected to be making changes to the |{package_check}| library, and the current command will be intercepted!')
                                logging.warning(
                                    'If you confirm that the change is necessary, add the parameter |-rules_open| and set it to |off|')
                if not len(lines) == 0:
                    with open(requirements, 'w', encoding=encoding) as file:
                        file.writelines(lines)

                    parameter_import += f' -r {requirements}'

    # Delete the garbage that was caused by file occupation when the package was unmounted
    if delete_cache:
        files_all = os.listdir(parent_path + '\\Lib\site-packages')
        for file in files_all:
            if file.startswith('~'):
                shutil.rmtree(parent_path + '\\Lib\site-packages\\' + delete_path)
                logging.info(f'{delete_path}The folder has been deleted')

    python_path = f'{parent_path}\\original_python.exe'

    # Deletes discarded variables to reduce memory usage
    # del rules_open, delete_cache, requirements, parent_path

    if run_check:
        logging.debug(f'{python_path} {parameter_import}')
        os.system(f"Powershell.exe {python_path} {parameter_import}")


parser = argparse.ArgumentParser(add_help=False)

parser.add_argument('-rules_open', type=bool, default=True, help='Whether or not to apply the rule')

parser.add_argument('-delete_cache', type=bool, default=False,
                    help='Delete the garbage that was caused by file occupation when the package was unmounted')

parser.add_argument('-debugging_information', type=bool, default=False,
                    help='Whether to output debug information')

known_args, unknown_args = parser.parse_known_args()

all_known_args = known_args.__dict__  # Convert known parameters into dictionary form

args = sys.argv[1:]

#  Get the index of the element
requirements_list = []
remove_element_and_next("-r")
remove_element_and_next("--requirement")

args_without_known = [arg for arg in unknown_args]

enable_rule = all_known_args['rules_open']
delete_uninstall_cache = all_known_args['delete_cache']

# Whether to output debug information (executed commands)
if all_known_args['debugging_information']:
    logging = get_logger(log_use.DEBUG)
else:
    logging = get_logger(log_use.INFO)

other_parameters = ' '.join(args_without_known)  # Other parameters are imported normally and are not detected

# Get the path to the current program
current_path = sys.argv[0]
# Get the parent directory of the path
execution_path = os.path.abspath(os.path.dirname(current_path))

# Remove useless variables to reduce memory usage
del all_known_args, args_without_known, known_args, unknown_args, args, current_path

try:
    run(parameter_import=other_parameters, rules_open=enable_rule, delete_cache=delete_uninstall_cache,
        parent_path=execution_path)
except Exception as error:
    logging.critical(error)
    logging.warning(f'Make sure that the |Inclusion_rules_package.txt| is in the |{execution_path}|')
