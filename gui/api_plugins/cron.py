#!/usr/bin/env python
"""API handlers for dealing with cron jobs."""

import itertools

from grr.gui import api_call_handler_base
from grr.gui import api_value_renderers

from grr.lib import aff4
from grr.lib import flow
from grr.lib.aff4_objects import cronjobs as aff4_cronjobs
from grr.lib.rdfvalues import grr_rdf
from grr.lib.rdfvalues import structs as rdf_structs

from grr.proto import api_pb2


CATEGORY = "Cron"


class ApiCronJob(rdf_structs.RDFProtoStruct):
  """ApiCronJob is used when rendering responses.

  ApiCronJob is meant to be more lightweight than automatically generated AFF4
  representation. It's also meant to contain only the information needed by
  the UI and and to not expose implementation defails.
  """
  protobuf = api_pb2.ApiCronJob

  def GetArgsClass(self):
    if self.flow_name:
      flow_cls = flow.GRRFlow.classes.get(self.flow_name)
      if flow_cls is None:
        raise ValueError("Flow %s not known by this implementation." %
                         self.flow_name)

      # The required protobuf for this class is in args_type.
      return flow_cls.args_type


def GetCronJobState(cron_job):
  """Returns state (as ApiCronJob.State) of an AFF4 cron job object."""
  if cron_job.Get(cron_job.Schema.DISABLED):
    return ApiCronJob.State.DISABLED
  else:
    return ApiCronJob.State.ENABLED


def IsCronJobFailing(cron_job):
  """Returns True if there are more than 1 failures during last 4 runs."""
  statuses = itertools.islice(
      cron_job.GetValuesForAttribute(cron_job.Schema.LAST_RUN_STATUS), 0, 4)

  failures_count = 0
  for status in statuses:
    if status.status != grr_rdf.CronJobRunStatus.Status.OK:
      failures_count += 1

  return failures_count >= 2


def CronJobToApiCronJob(cron_job):
  """Converts AFF4 CronJob to api-friendly ApiCronJob."""
  cron_args = cron_job.Get(cron_job.Schema.CRON_ARGS)

  api_cron_job = ApiCronJob(urn=cron_job.urn,
                            description=cron_args.description,
                            flow_name=cron_args.flow_runner_args.flow_name,
                            flow_runner_args=cron_args.flow_runner_args,
                            periodicity=cron_args.periodicity,
                            lifetime=cron_args.lifetime,
                            allow_overruns=cron_args.allow_overruns,
                            state=GetCronJobState(cron_job),
                            last_run_time=cron_job.Get(
                                cron_job.Schema.LAST_RUN_TIME),
                            is_failing=IsCronJobFailing(cron_job))
  try:
    api_cron_job.flow_args = cron_args.flow_args
  except ValueError:
    # If args class name has changed, ValueError will be raised. Handling
    # this gracefully - we should still try to display some useful info
    # about the flow.
    pass

  return api_cron_job


class ApiListCronJobsArgs(rdf_structs.RDFProtoStruct):
  protobuf = api_pb2.ApiListCronJobsArgs


class ApiListCronJobsHandler(api_call_handler_base.ApiCallHandler):
  """Lists flows launched on a given client."""

  category = CATEGORY
  args_type = ApiListCronJobsArgs

  def Render(self, args, token=None):
    if not args.count:
      stop = None
    else:
      stop = args.offset + args.count

    cron_jobs_urns = list(itertools.islice(
        aff4_cronjobs.CRON_MANAGER.ListJobs(token=token), args.offset, stop))
    cron_jobs = aff4.FACTORY.MultiOpen(
        cron_jobs_urns, aff4_type="CronJob", token=token, age=aff4.ALL_TIMES)

    items = [CronJobToApiCronJob(cron_job) for cron_job in cron_jobs]
    result = dict(offset=args.offset,
                  count=len(items),
                  items=api_value_renderers.RenderValue(items))
    return result


class ApiCreateCronJobHandler(api_call_handler_base.ApiCallHandler):
  """Creates a new cron job."""

  category = CATEGORY
  args_type = ApiCronJob

  privileged = True

  def Render(self, args, token=None):
    if args.flow_name and not args.flow_runner_args.flow_name:
      args.flow_runner_args.flow_name = args.flow_name

    cron_args = aff4_cronjobs.CreateCronJobFlowArgs(
        description=args.description,
        periodicity=args.periodicity,
        flow_runner_args=args.flow_runner_args,
        flow_args=args.flow_args,
        allow_overruns=args.allow_overruns,
        lifetime=args.lifetime)
    urn = aff4_cronjobs.CRON_MANAGER.ScheduleFlow(
        cron_args=cron_args, disabled=True, token=token)

    fd = aff4.FACTORY.Open(urn, aff4_type="CronJob", token=token,
                           age=aff4.ALL_TIMES)
    api_cron_job = CronJobToApiCronJob(fd)

    return api_value_renderers.RenderValue(api_cron_job)
