import os
import yaml
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _generate_changelog(old_blueprint, new_blueprint):
    """
    Compares two YAML blueprints and extracts key changes.
    
    :param old_blueprint: The old blueprint content as dictionary.
    :param new_blueprint: The new blueprint content as dictionary.
    :return: A dictionary of changes.
    """
    changes = {}
    try:
        name_changed = old_blueprint.get('name') != new_blueprint.get('name')
        if name_changed:
            changes['name'] = {'old': old_blueprint.get('name'), 'new': new_blueprint.get('name')}
            logging.info('Name changed from %s to %s',
                         old_blueprint.get('name'), new_blueprint.get('name'))
        
        description_changed = old_blueprint.get('description') != new_blueprint.get('description')
        if description_changed:
            changes['description'] = {'old': old_blueprint.get('description'), 'new': new_blueprint.get('description')}
            logging.info('Description changed from %s to %s',
                         old_blueprint.get('description'), new_blueprint.get('description'))

        version_changed = old_blueprint.get('version') != new_blueprint.get('version')
        if version_changed:
            changes['version'] = {'old': old_blueprint.get('version'), 'new': new_blueprint.get('version')}
            logging.info('Version changed from %s to %s',
                         old_blueprint.get('version'), new_blueprint.get('version'))

        input_variables_old = set(old_blueprint.get('input_variables', []))
        input_variables_new = set(new_blueprint.get('input_variables', []))
        input_changes = input_variables_new.difference(input_variables_old)
        if input_changes:
            changes['input_variables'] = {'added': list(input_changes)}
            logging.info('Input variables changed, added: %s', input_changes)

    except Exception as e:
        logging.error('Error generating changelog: %s', e)
    return changes


def _find_oldest_backup_by_ctime(backup_folder):
    """
    Finds the oldest backup file by creation time.
    
    :param backup_folder: The folder where backups are stored.
    :return: The path to the oldest backup file or None if not found.
    """
    try:
        backups = [os.path.join(backup_folder, f) for f in os.listdir(backup_folder) if os.path.isfile(os.path.join(backup_folder, f))]
        oldest_backup = min(backups, key=os.path.getctime, default=None)
        logging.info('Oldest backup found: %s', oldest_backup)
        return oldest_backup
    except Exception as e:
        logging.error('Error finding oldest backup: %s', e)
        return None


def _get_backup_content(backup_file):
    """
    Safely reads backup file content with error handling.
    
    :param backup_file: The backup file path.
    :return: Content of the backup file or None if an error occurred.
    """
    try:
        with open(backup_file, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f'Backup file {backup_file} not found.')
    except yaml.YAMLError as yaml_err:
        logging.error(f'Error parsing YAML in {backup_file}: {yaml_err}')
    except PermissionError:
        logging.error(f'Permission denied for file {backup_file}.')
    except Exception as e:
        logging.error(f'Unexpected error reading {backup_file}: {e}')
    return None

