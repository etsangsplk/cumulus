""" Bundling functions """
import logging
import os
import os.path
import subprocess
import sys
import tarfile

import config_handler
import connection_handler

logger = logging.getLogger(__name__)


def build_bundles():
    """ Build bundles for the environment """
    for bundle in config_handler.get_bundles():
        logger.info('Building bundle {}'.format(bundle))
        logger.debug('Bundle paths: {}'.format(', '.join(
            config_handler.get_bundle_paths(bundle))))

        # Run pre-bundle-hook
        _pre_bundle_hook(bundle)

        bundle_path = _bundle(
            bundle,
            config_handler.get_environment(),
            config_handler.get_environment_option('version'),
            config_handler.get_bundle_paths(bundle))

        # Run post-bundle-hook
        _post_bundle_hook(bundle)

        _upload_bundle(bundle_path)

    _upload_bundle_handler()


def _bundle(bundle_name, environment, version, paths):
    """ Create bundle

    :type bundle: str
    :param bundle: Bundle name
    :type environment: str
    :param environment: Environment name
    :type version: str
    :param version: Version number
    :type paths: list
    :param paths: List of paths to include
    """
    # Define a filter to modify the tar object
    def tar_filter(tarinfo):
        """ Modify the tar object.

        See: http://docs.python.org/library/tarfile.html#tarfile.TarInfo
        """
        # Make sure that the files are placed in the / root dir
        tarinfo.name = tarinfo.name.replace(
            '{}/'.format(path[1:]),
            '')
        tarinfo.name = tarinfo.name.replace(
            '{}'.format(path[1:]),
            '')

        for rewrite in path_rewrites:
            try:
                if tarinfo.name[:len(rewrite['target'])] == rewrite['target']:
                    tarinfo.name = tarinfo.name.replace(
                        rewrite['target'],
                        rewrite['destination'])
                    logger.debug('Replaced {} with {}'.format(
                        rewrite['target'], rewrite['destination']))
            except IndexError:
                pass

        # Remove prefixes
        tarinfo.name = tarinfo.name.replace(
            '__cumulus-{}__'.format(environment),
            '')

        # Change user permissions on all files
        tarinfo.uid = 0
        tarinfo.gid = 0
        tarinfo.uname = 'root'
        tarinfo.gname = 'root'

        return tarinfo

    def exclusion_filter(filename):
            """ Filter excluding files for other environments """
            prefix = '__cumulus-{}__'.format(environment)
            if os.path.basename(filename).startswith('__cumulus-'):
                cnt = len(os.path.basename(filename).split(prefix))
                if cnt == 2:
                    return False
                else:
                    logger.debug('Excluding file {}'.format(filename))
                    return True
            elif prefix in filename.split(os.path.sep):
                logger.debug('Excluding file {}'.format(filename))
                return True
            else:
                return False

    bundle = '{}/target/bundle-{}-{}-{}.tar.bz2'.format(
        os.curdir,
        environment,
        version,
        bundle_name)

    path_rewrites = config_handler.get_bundle_path_rewrites(bundle_name)

    # Ensure that the bundle target exists
    if not os.path.exists(os.path.dirname(bundle)):
        os.makedirs(os.path.dirname(bundle))

    tar = tarfile.open(bundle, 'w:bz2', dereference=True)
    for path in paths:
        tar.add(
            path,
            exclude=exclusion_filter,
            filter=tar_filter)
    tar.close()
    logger.info('Wrote bundle to {}'.format(bundle))

    return bundle


def _post_bundle_hook(bundle_name):
    """ Execute a post-bundle-hook

    :type bundle: str
    :param bundle: Bundle name
    """
    command = config_handler.get_post_bundle_hook(bundle_name)

    if not command:
        return None

    logger.info('Running post-bundle-hook command: "{}"'.format(command))
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError, error:
        logger.error(
            'The post-bundle-hook returned a non-zero exit code: {}'.format(
                error))
        sys.exit(1)


def _pre_bundle_hook(bundle_name):
    """ Execute a pre-bundle-hook

    :type bundle: str
    :param bundle: Bundle name
    """
    command = config_handler.get_pre_bundle_hook(bundle_name)

    if not command:
        return None

    logger.info('Running pre-bundle-hook command: "{}"'.format(command))
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError, error:
        logger.error(
            'The pre-bundle-hook returned a non-zero exit code: {}'.format(
                error))
        sys.exit(1)


def _upload_bundle(bundle_path):
    """ Upload all bundles to S3

    :type bundle_path: str
    :param bundle_path: Local path to the bundle
    """
    connection = connection_handler.connect_s3()
    bucket = connection.get_bucket(
        config_handler.get_environment_option('bucket'))

    key_name = '{}/{}/{}'.format(
        config_handler.get_environment(),
        config_handler.get_environment_option('version'),
        os.path.basename(bundle_path))
    key = bucket.new_key(key_name)
    logger.info('Starting upload of {}'.format(
        os.path.basename(bundle_path)))
    key.set_contents_from_filename(bundle_path, replace=True)
    logger.info('Completed upload of {}'.format(
        os.path.basename(bundle_path)))


def _upload_bundle_handler():
    """ Upload the bundle handler to S3 """
    connection = connection_handler.connect_s3()
    bucket = connection.get_bucket(
        config_handler.get_environment_option('bucket'))

    logger.info('Uploading the cumulus_bundle_handler.py script')
    key_name = '{}/{}/cumulus_bundle_handler.py'.format(
        config_handler.get_environment(),
        config_handler.get_environment_option('version'))
    key = bucket.new_key(key_name)
    key.set_contents_from_filename(
        '{}/bundle_handler/cumulus_bundle_handler.py'.format(
            os.path.dirname(os.path.realpath(__file__))),
        replace=True)
