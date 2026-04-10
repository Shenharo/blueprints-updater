def _generate_changelog(old_yaml_dict, new_yaml_dict):
    # Compare two YAML dictionaries and format the changelog
    changelog_lines = []
    for key in new_yaml_dict:
        if key not in old_yaml_dict:
            changelog_lines.append(f"Added: {key}: {new_yaml_dict[key]}")
        elif new_yaml_dict[key] != old_yaml_dict[key]:
            changelog_lines.append(f"Changed: {key} from {old_yaml_dict[key]} to {new_yaml_dict[key]}")
    for key in old_yaml_dict:
        if key not in new_yaml_dict:
            changelog_lines.append(f"Removed: {key}")
    return '\n'.join(changelog_lines)


def _find_oldest_backup_by_ctime(path, max_backups):
    import os
    backups = [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    backups.sort(key=os.path.getctime)
    return backups[:max_backups]


def _get_backup_content_safe(backup_path):
    import yaml
    try:
        with open(backup_path, 'r') as file:
            content = yaml.safe_load(file)
        return content
    except Exception as e:
        # handle errors such as invalid YAML, permissions issues
        return None


def _generate_changelog_for_scenario(path, local_content, remote_content):
    # Handle changelog scenarios and generate the appropriate changelog
    # Scenario 1: Remote changed, local unchanged
    # Scenario 2: Local changed by user
    # Scenario 3: Both changed
    if local_content == remote_content:
        # Case where remote is changed
        return _generate_changelog(fetch_old_yaml(local_content), remote_content)
    else:
        oldest_backup = _find_oldest_backup_by_ctime(path, 1)
        if oldest_backup:
            backup_content = _get_backup_content_safe(oldest_backup[0])
            if backup_content:
                return _generate_changelog(backup_content, remote_content)
    return "No changes detected"