# example.py Code Sample
#
# Copyright (c) Microsoft and contributors.  All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import azure.mgmt.netapp.models
import os
import sample_utils
import sys
import resource_uri_utils
from haikunator import Haikunator
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.netapp import AzureNetAppFilesManagementClient
from azure.mgmt.netapp.models import NetAppAccount, \
    CapacityPool, \
    Volume, \
    ExportPolicyRule, \
    VolumePropertiesExportPolicy, \
    ActiveDirectory
from azure.mgmt.resource import ResourceManagementClient
from getpass import getpass
from msrestazure.azure_exceptions import CloudError
from sample_utils import console_output, print_header, resource_exists

SHOULD_CLEANUP = False
LOCATION = 'eastus'
RESOURCE_GROUP_NAME = 'anf01-rg'
VNET_NAME = 'photoscan-vnet'
SUBNET_NAME = 'anf-sn'
VNET_RESOURCE_GROUP_NAME = 'photoscan-rg'
ANF_ACCOUNT_NAME = Haikunator().haikunate(delimiter='')
CAPACITYPOOL_NAME = "Pool01"
CAPACITYPOOL_SERVICE_LEVEL = "Standard"
CAPACITYPOOL_SIZE = 4398046511104  # 4TiB
VOLUME_NAME = 'Vol-{}-{}'.format(ANF_ACCOUNT_NAME, CAPACITYPOOL_NAME)
VOLUME_USAGE_QUOTA = 107374182400  # 100GiB

# SMB related variables
DOMAIN_JOIN_USERNAME = 'pmcadmin'
DNS_LIST = '10.0.2.4,10.0.2.5' # Please notice that this is a comma-separated string
AD_FQDN = 'testdomain.local'
SMB_SERVERNAME_PREFIX = 'pmcsmb' # this needs to be maximum 10 characters in length and during the domain join process a random string gets appended.

# Resource SDK related (change only if API version is not supported anymore)
VIRTUAL_NETWORKS_SUBNET_API_VERSION = '2018-11-01'


def create_account(client, resource_group_name, anf_account_name, location,
                   active_directories=None, tags=None):
    """Creates an Azure NetApp Files Account

    Function that creates an Azure NetApp Account, which requires building the
    account body object first.

    Args:
        client (AzureNetAppFilesManagementClient): Azure Resource Provider
            Client designed to interact with ANF resources
        resource_group_name (string): Name of the resource group where the
            account will be created
        location (string): Azure short name of the region where resource will
            be deployed
        tags (object): Optional. Key-value pairs to tag the resource, default
            value is None. E.g. {'cc':'1234','dept':'IT'}
        active_directories (list[ActiveDirectory]): Optional. List of
            ActiveDirectories objects

    Returns:
        NetAppAccount: Returns the newly created NetAppAccount resource
    """

    account_body = NetAppAccount(location=location,
        tags=tags,
        active_directories=active_directories)

    return client.accounts.create_or_update(account_body,
                                            resource_group_name,
                                            anf_account_name).result()


def create_capacitypool_async(client, resource_group_name, anf_account_name,
                              capacitypool_name, service_level, size, location,
                              tags=None):
    capacitypool_body = CapacityPool(
        location=location,
        service_level=service_level,
        size=size)
    """Creates a capacity pool within an account

    Function that creates a Capacity Pool, capacity pools are needed to define
    maximum service level and capacity.

    Args:
        client (AzureNetAppFilesManagementClient): Azure Resource Provider
            Client designed to interact with ANF resources
        resource_group_name (string): Name of the resource group where the
            capacity pool will be created, it needs to be the same as the
            Account
        anf_account_name (string): Name of the Azure NetApp Files Account where
            the capacity pool will be created
        capacitypool_name (string): Capacity pool name
        service_level (string): Desired service level for this new capacity
            pool, valid values are "Ultra","Premium","Standard"
        size (long): Capacity pool size, values range from 4398046511104
            (4TiB) to 549755813888000 (500TiB)
        location (string): Azure short name of the region where resource will
            be deployed, needs to be the same as the account
        tags (object): Optional. Key-value pairs to tag the resource, default
            value is None. E.g. {'cc':'1234','dept':'IT'}

    Returns:
        CapacityPool: Returns the newly created capacity pool resource
    """

    return client.pools.create_or_update(capacitypool_body,
                                         resource_group_name,
                                         anf_account_name,
                                         capacitypool_name).result()


def create_volume(client, resource_group_name, anf_account_name,
                  capacitypool_name, volume_name, volume_usage_quota,
                  service_level, subnet_id, location, tags=None):

    """Creates a volume within a capacity pool

    Function that in this example creates a SMB volume within a capacity
    pool, as a note service level needs to be the same as the capacity pool.
    This function also defines the volume body as the configuration settings
    of the new volume.

    Args:
        client (AzureNetAppFilesManagementClient): Azure Resource Provider
            Client designed to interact with ANF resources
        resource_group_name (string): Name of the resource group where the
            volume will be created, it needs to be the same as the account
        anf_account_name (string): Name of the Azure NetApp Files Account where
            the capacity pool holding the volume exists
        capacitypool_name (string): Capacity pool name where volume will be
            created
        volume_name (string): Volume name
        volume_usage_quota (long): Volume size in bytes, minimum value is
            107374182400 (100GiB), maximum value is 109951162777600 (100TiB)
        service_level (string): Volume service level, needs to be the same as
            the capacity pool, valid values are "Ultra","Premium","Standard"
        subnet_id (string): Subnet resource id of the delegated to ANF Volumes
            subnet
        location (string): Azure short name of the region where resource will
            be deployed, needs to be the same as the account
        tags (object): Optional. Key-value pairs to tag the resource, default
            value is None. E.g. {'cc':'1234','dept':'IT'}

    Returns:
        Volume: Returns the newly created volume resource
    """

    volume_body = Volume(
        usage_threshold=volume_usage_quota,
        creation_token=volume_name,
        location=location,
        service_level=service_level,
        subnet_id=subnet_id,
        protocol_types=["CIFS"]) # Despite of this being an array, only one protocol is supported at this time

    return client.volumes.create_or_update(volume_body,
                                           resource_group_name,
                                           anf_account_name,
                                           capacitypool_name,
                                           volume_name).result()


def run_example():
    """Azure NetApp Files SDK management example."""

    print_header("Azure NetAppFiles Python SDK Sample - Sample "
        "project that creates a SMB Volume with Azure NetApp "
        "Files SDK with Python")
    
    # Getting Active Directory Identity's password
    domain_join_user_password = getpass(
        ("Please type Active Directory's user password that will "
        "domain join ANF's SMB server and press [ENTER]:"))

    if len(domain_join_user_password) == 0:
        console_output(
            'An error ocurred. Password cannot be empty string')
        raise Exception('Password cannot be empty string')

    # Creating the Azure NetApp Files Client with an Application
    # (service principal) token provider
    credentials, subscription_id = sample_utils.get_credentials()
    anf_client = AzureNetAppFilesManagementClient(
        credentials, subscription_id)

    resources_client = ResourceManagementClient(credentials, subscription_id)

    # Checking if vnet/subnet information leads to a valid resource
    SUBNET_ID = '/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Network/virtualNetworks/{}/subnets/{}'.format(
        subscription_id, VNET_RESOURCE_GROUP_NAME, VNET_NAME, SUBNET_NAME)

    result = resource_exists(resources_client, 
        SUBNET_ID, 
        VIRTUAL_NETWORKS_SUBNET_API_VERSION)

    if not result:
        console_output("ERROR: Subnet not with id {} not found".format(
            SUBNET_ID))
        raise Exception("Subnet not found error. Subnet Id {}".format(
            SUBNET_ID))

    # Creating an Azure NetApp Account
    
    '''
    Building the ActiveDirectories object to be passed down to 
    create_account() function. Notice that this is a list but only one
    active directory configuration is supported per subscription and 
    region at the time this sample was first published 
    '''
    active_directories = [ActiveDirectory(
       dns=DNS_LIST,
       domain=AD_FQDN,
       username=DOMAIN_JOIN_USERNAME,
       password=domain_join_user_password,
       smb_server_name=SMB_SERVERNAME_PREFIX)]


    console_output('Creating Azure NetApp Files account ...')
    account = None
    try:
        account = create_account(anf_client,
                                 RESOURCE_GROUP_NAME,
                                 ANF_ACCOUNT_NAME,
                                 LOCATION,
                                 active_directories)
        console_output(
            '\tAccount successfully created, resource id: {}'
            .format(account.id))
    except CloudError as ex:
        console_output(
            'An error ocurred. Error details: {}'.format(ex.message))
        raise

    # Creating a Capacity Pool
    console_output('Creating Capacity Pool ...')
    capacity_pool = None
    try:
        capacity_pool = create_capacitypool_async(anf_client,
                                                  RESOURCE_GROUP_NAME,
                                                  account.name,
                                                  CAPACITYPOOL_NAME,
                                                  CAPACITYPOOL_SERVICE_LEVEL,
                                                  CAPACITYPOOL_SIZE,
                                                  LOCATION)
        console_output('\tCapacity Pool successfully created, resource id: {}'
                       .format(capacity_pool.id))
    except CloudError as ex:
        console_output(
            'An error ocurred. Error details: {}'.format(ex.message))
        raise

    
    # Creating a Volume

    '''    
    Note: With exception of Accounts, all resources with Name property
    returns a relative path up to the name and to use this property in
    other methods, like Get for example, the argument needs to be
    sanitized and just the actual name needs to be used (the hierarchy
    needs to be cleaned up in the name).
    Capacity Pool Name property example: "pmarques-anf01/pool01"
    "pool01" is the actual name that needs to be used instead. Below
    you will see a sample function that parses the name from its
    resource id: resource_uri_utils.get_anf_capacity_pool()
    '''

    console_output('Creating a Volume ...')

    volume = None
    try:
        pool_name = resource_uri_utils.get_anf_capacity_pool(capacity_pool.id)

        volume = create_volume(anf_client,
                               RESOURCE_GROUP_NAME,
                               account.name,
                               pool_name,
                               VOLUME_NAME,
                               VOLUME_USAGE_QUOTA,
                               CAPACITYPOOL_SERVICE_LEVEL,
                               SUBNET_ID,
                               LOCATION)
        console_output(
            '\tVolume successfully created, resource id: {}'.format(volume.id))
    except CloudError as ex:
        console_output(
            'An error ocurred. Error details: {}'.format(ex.message))
        raise

    '''
    Cleaning up volumes - for this to happen, please change the value of
    SHOULD_CLEANUP variable to true.
    Note: Volume deletion operations at the RP level are executed serially
    '''
    if SHOULD_CLEANUP:
        '''
        Cleaning up. This process needs to start the cleanup from the
        innermost resources down in the hierarchy chain in our case
        Snapshots->Volumes->Capacity Pools->Accounts
        '''
        console_output('Cleaning up...')

        console_output("\tDeleting Volumes...")
        try:
            volume_ids = [volume.id]
            for volume_id in volume_ids:
                console_output("\t\tDeleting {}".format(volume_id))
                anf_client.volumes.delete(RESOURCE_GROUP_NAME,
                                          account.name,
                                          resource_uri_utils.get_anf_capacitypool(
                                              capacity_pool.id),
                                          resource_uri_utils.get_anf_volume(
                                              volume_id)
                                          ).wait()

                # ARM Workaround to wait the deletion complete/propagate
                sample_utils.wait_for_no_anf_resource(anf_client, volume_id)

                console_output('\t\tDeleted Volume: {}'.format(volume_id))
        except CloudError as ex:
            console_output(
                'An error ocurred. Error details: {}'.format(ex.message))
            raise

        # Cleaning up Capacity Pool
        console_output("\tDeleting Capacity Pool {} ...".format(
            resource_uri_utils.get_anf_capacitypool(capacity_pool.id)))
        try:
            anf_client.pools.delete(RESOURCE_GROUP_NAME,
                                    account.name,
                                    resource_uri_utils.get_anf_capacitypool(
                                        capacity_pool.id)
                                    ).wait()

            # ARM Workaround to wait the deletion complete/propagate
            sample_utils.wait_for_no_anf_resource(anf_client, capacity_pool.id)

            console_output(
                '\t\tDeleted Capacity Pool: {}'.format(capacity_pool.id))
        except CloudError as ex:
            console_output(
                'An error ocurred. Error details: {}'.format(ex.message))
            raise

        # Cleaning up Account
        console_output("\tDeleting Account {} ...".format(account.name))
        try:
            anf_client.accounts.delete(RESOURCE_GROUP_NAME, account.name)
            console_output('\t\tDeleted Account: {}'.format(account.id))
        except CloudError as ex:
            console_output(
                'An error ocurred. Error details: {}'.format(ex.message))
            raise

'''
This script expects that the following environment var is set:

AZURE_AUTH_LOCATION: contains path for azureauth.json file

File content (and how to generate) is documented at
https://docs.microsoft.com/en-us/dotnet/azure/dotnet-sdk-azure-authenticate?view=azure-dotnet
'''

if __name__ == "__main__":

    run_example()
