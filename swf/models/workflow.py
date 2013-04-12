# -*- coding:utf-8 -*-

# Copyright (c) 2013, Theo Crevon
# Copyright (c) 2013, Greg Leclercq
#
# See the file LICENSE for copying permission.

import time
import collections

from boto.swf.exceptions import SWFResponseError, SWFTypeAlreadyExistsError

from swf.constants import REGISTERED
from swf.core import ConnectedSWFObject
from swf.models import BaseModel
from swf.models.base import Diff
from swf.models.event import History
from swf.exceptions import DoesNotExistError, AlreadyExistsError,\
                           ResponseError


_POLICIES = ('TERMINATE',       # child executions will be terminated
             'REQUEST_CANCEL',  # a request to cancel will be attempted for
                                # each child execution
             'ABANDON',         # no action will be taken
)

CHILD_POLICIES = collections.namedtuple('CHILD_POLICY',
                                        ' '.join(_POLICIES))(*_POLICIES)


class WorkflowType(BaseModel):
    """Simple Workflow Type wrapper

    :param  domain: Domain the workflow type should be registered in
    :type   domain: swf.models.Domain

    :param  name: name of the workflow type
    :type   name: String

    :param  version: workflow type version
    :type   version: String

    :param  status: workflow type status
    :type   status: swf.core.ConnectedSWFObject.{REGISTERED, DEPRECATED}

    :param   creation_date: creation date of the current WorkflowType
    :type    creation_date: float (timestamp)

    :param   deprecation_date: deprecation date of WorkflowType
    :type    deprecation_date: float (timestamp)

    :param  task_list: task list to use for scheduling decision tasks for executions
                       of this workflow type
    :type   task_list: String

    :param  child_policy: policy to use for the child workflow executions
                          when a workflow execution of this type is terminated
    :type   child_policy: CHILD_POLICIES.{TERMINATE |
                                          REQUEST_CANCEL |
                                          ABANDON}

    :param  execution_timeout: maximum duration for executions of this workflow type
    :type   execution_timeout: String

    :param  decision_tasks_timeout: maximum duration of decision tasks for this workflow type
    :type   decision_tasks_timeout: String

    :param  description: Textual description of the workflow type
    :type   description: String
    """
    def __init__(self, domain, name, version,
                 status=REGISTERED,
                 creation_date=0.0,
                 deprecation_date=0.0,
                 task_list=None,
                 child_policy=CHILD_POLICIES.TERMINATE,
                 execution_timeout='300',
                 decision_tasks_timeout='300',
                 description=None, *args, **kwargs):
        super(WorkflowType, self).__init__(*args, **kwargs)
        self.domain = domain
        self.name = name
        self.version = version
        self.status = status
        self.creation_date = creation_date
        self.deprecation_date = deprecation_date

        self.task_list = task_list
        self.execution_timeout = execution_timeout
        self.decision_tasks_timeout = decision_tasks_timeout
        self.description = description

        # Explicitly call child_policy setter
        # to validate input value
        self.child_policy = child_policy

    @property
    def child_policy(self):
        if not hasattr(self, '_child_policy'):
            self._child_policy = None

        return self._child_policy

    @child_policy.setter
    def child_policy(self, policy):
        if not policy in CHILD_POLICIES:
            raise ValueError("invalid child policy value: {}".format(policy))

        self._child_policy = policy

    def _diff(self):
        """Checks for differences between WorkflowType instance
        and upstream version

        :returns: A list of swf.models.base.Diff namedtuple describing
                  differences
        :rtype: list
        """
        try:
            description = self.connection.describe_workflow_type(
                self.domain.name,
                self.name,
                self.version
            )
        except SWFResponseError as e:
            if e.error_code == 'UnknownResourceFault':
                raise DoesNotExistError("Remote Domain does not exist")

            raise ResponseError(e.body['message'])

        workflow_info = description['typeInfo']
        workflow_config = description['configuration']

        attributes_comparison = [
            Diff('name', self.name, workflow_info['workflowType']['name']),
            Diff('version', self.version, workflow_info['workflowType']['version']),
            Diff('status', self.status, workflow_info['status']),
            Diff('creation_date', self.creation_date, workflow_info['creationDate']),
            Diff('deprecation_date', self.deprecation_date, workflow_info['deprecationDate']),
            Diff('task_list', self.task_list, workflow_config['defaultTaskList']['name']),
            Diff('child_policy', self.child_policy, workflow_config['defaultChildPolicy']),
            Diff('execution_timeout', self.execution_timeout, workflow_config['defaultExecutionStartToCloseTimeout']),
            Diff('decision_tasks_timout', self.decision_tasks_timeout, workflow_config['defaultTaskStartToCloseTimeout']),
            Diff('description', self.description, workflow_info['description']),
        ]

        return filter(
            lambda data: data[1] != data[2],
            attributes_comparison
        )

    @property
    def exists(self):
        """Checks if the WorkflowType exists amazon-side

        :rtype: bool
        """
        try:
            description = self.connection.describe_workflow_type(
                self.domain.name,
                self.name,
                self.version
            )
        except SWFResponseError as e:
            if e.error_code != 'UnknownResourceFault':
                raise ResponseError(e.body['message'])

            return False

        return True

    @property
    def is_synced(self):
        """Checks if WorkflowType instance has changes, comparing
        with remote object representation

        :rtype: bool
        """
        return super(WorkflowType, self).is_synced

    @property
    def changes(self):
        """Returns changes between WorkflowType instance, and
        remote object representation

        :returns: A list of swf.models.base.Diff namedtuple describing
                  differences
        :rtype: list
        """
        return super(WorkflowType, self).changes

    def save(self):
        """Creates the workflow type amazon side"""
        try:
            self.connection.register_workflow_type(
                self.domain.name,
                self.name,
                self.version,
                task_list=str(self.task_list),
                default_child_policy=str(self.child_policy),
                default_execution_start_to_close_timeout=str(self.execution_timeout),
                default_task_start_to_close_timeout=str(self.decision_tasks_timeout),
                description=self.description
            )
        except SWFTypeAlreadyExistsError:
            raise AlreadyExistsError("Workflow type %s already exists amazon-side" % self.name)
        except SWFResponseError as e:
            if e.error_code == 'UnknownResourceFault':
                raise DoesNotExistError(e.body['message'])

    def delete(self):
        """Deprecates the workflow type amazon-side"""
        try:
            self.connection.deprecate_workflow_type(self.domain.name, self.name, self.version)
        except SWFResponseError as e:
            if e.error_code in ['UnknownResourceFault', 'TypeDeprecatedFault']:
                raise DoesNotExistError(e.body['message'])

    def start_execution(self, workflow_id=None, task_list=None,
                        child_policy=None, execution_timeout=None,
                        input=None, tag_list=None, decision_tasks_timeout=None):
        """Starts a Workflow execution of current workflow type

        :param  workflow_id: The user defined identifier associated with the workflow execution
        :type   workflow_id: String

        :param  task_list: task list to use for scheduling decision tasks for execution
                        of this workflow
        :type   task_list: String

        :param  child_policy: policy to use for the child workflow executions
                              of this workflow execution.
        :type   child_policy: CHILD_POLICIES.{TERMINATE |
                                              REQUEST_CANCEL |
                                              ABANDON}

        :param  execution_timeout: maximum duration for the workflow execution
        :type   execution_timeout: String

        :param  input: Input of the workflow execution
        :type   input: String

        :param  tag_list: Tags associated with the workflow execution
        :type   tag_list: String

        :param  decision_tasks_timeout: maximum duration of decision tasks
                                        for this workflow execution
        :type   decision_tasks_timeout: String
        """
        workflow_id = workflow_id or '%s-%s-%i' % (self.name, self.version, time.time())
        task_list = task_list or self.task_list
        child_policy = child_policy or self.child_policy

        run_id = self.connection.start_workflow_execution(
            self.domain.name,
            workflow_id,
            self.name,
            self.version,
            task_list=task_list,
            child_policy=child_policy,
            execution_start_to_close_timeout=execution_timeout,
            input=input,
            tag_list=tag_list,
            task_start_to_close_timeout=decision_tasks_timeout,
        )['runId']

        return WorkflowExecution(self.domain, workflow_id, run_id)

    def __repr__(self):
        return '<{} domain={} name={} version={} status={}>'.format(
               self.__class__.__name__,
               self.domain.name,
               self.name,
               self.version,
               self.status)


class WorkflowExecution(BaseModel):
    """Simple Workflow execution wrapper

    :param  domain: Domain the workflow execution should be registered in
    :type   domain: swf.models.domain.Domain

    :param  workflow_type: The WorkflowType associated with the workflow execution
                           is associated with
    :type   workflow_type: String

    :param  workflow_id: The user defined identifier associated with the workflow execution
    :type   workflow_id: String

    :param  run_id: The Amazon defined identifier associated with the workflow execution
    :type   run_id: String

    :param  status: Whether the WorkflowExecution instance represents an opened or
                    closed execution
    :type   status: String constant
    """
    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"

    CLOSE_STATUS_COMPLETED = "COMPLETED"
    CLOSE_STATUS_FAILED = "FAILED"
    CLOSE_STATUS_CANCELED = "CANCELED"
    CLOSE_STATUS_TERMINATED = "TERMINATED"
    CLOSE_STATUS_CONTINUED_AS_NEW = "CLOSE_STATUS_CONTINUED_AS_NEW"
    CLOSE_TIMED_OUT = "TIMED_OUT"

    def __init__(self, domain, workflow_type,
                 workflow_id, run_id=None,
                 status=STATUS_OPEN, task_list=None,
                 child_policy=None, execution_timeout=None,
                 input=None, tag_list=None,
                 decision_tasks_timeout=None, *args, **kwargs):
        super(WorkflowExecution, self).__init__(*args, **kwargs)

        self.domain = domain
        self.workflow_id = workflow_id
        self.run_id = run_id
        self.status = status
        self.task_list = task_list
        self.child_policy = child_policy
        self.execution_timeout = execution_timeout
        self.input = input
        self.tag_list = tag_list or []
        self.decision_tasks_timeout = decision_tasks_timeout

    def _diff(self):
        """Checks for differences between WorkflowExecution instance
        and upstream version

        :returns: A list of swf.models.base.Diff namedtuple describing
                  differences
        :rtype: list
        """
        try:
            description = self.connection.describe_workflow_execution(
                self.domain.name,
                self.run_id,
                self.workflow_id
            )
        except SWFResponseError as e:
            if e.error_code == 'UnknownResourceFault':
                raise DoesNotExistError("Remote Domain does not exist")

            raise ResponseError(e.body['message'])

        execution_info = description['executionInfo']
        execution_config = description['executionConfiguration']

        attributes_comparison = [
            Diff('workflow_id', self.workflow_id, execution_info['execution']['workflowId']),
            Diff('run_id', self.run_id, execution_info['execution']['runId']),
            Diff('status',  self.status, execution_info['executionStatus']),
            Diff('task_list', self.task_list, execution_config['taskList']['name']),
            Diff('child_policy',  self.child_policy, execution_config['childPolicy']),
            Diff('execution_timeout', self.execution_timeout, execution_config['executionStartToCloseTimeout']),
            Diff('tag_list', self.tag_list, execution_info['tagList']),
            Diff('decision_tasks_timeout', self.decision_tasks_timeout, execution_config['taskStartToCloseTimeout']),
        ]

        return filter(
            lambda data: data[1] != data[2],
            attributes_comparison
        )

    @property
    def exists(self):
        """Checks if the WorkflowExecution exists amazon-side

        :rtype: bool
        """
        try:
            description = self.connection.describe_workflow_execution(
                self.domain.name,
                self.run_id,
                self.workflow_id
            )
        except SWFResponseError as e:
            if e.error_code != 'UnknownResourceFault':
                raise ResponseError(e.body['message'])

            return False

        return True

    @property
    def is_synced(self):
        """Checks if WorkflowExecution instance has changes, comparing
        with remote object representation

        :rtype: bool
        """
        return super(WorkflowExecution, self).is_synced

    @property
    def changes(self):
        """Returns changes between WorkflowExecution instance, and
        remote object representation

        :returns: A list of swf.models.base.Diff namedtuple describing
                  differences
        :rtype: list
        """
        return super(WorkflowExecution, self).changes

    def history(self, *args, **kwargs):
        """Returns workflow execution history report

        :returns: The workflow execution complete events history
        :rtype: swf.models.event.History
        """
        event_list = self.connection.get_workflow_execution_history(
            self.domain.name,
            self.run_id,
            self.workflow_id,
            **kwargs
        )['events']

        return History.from_event_list(event_list)
