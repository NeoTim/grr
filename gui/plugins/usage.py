#!/usr/bin/env python
"""GUI elements to display usage statistics."""


import operator

from grr.gui import renderers
from grr.gui.plugins import semantic
from grr.gui.plugins import statistics
from grr.lib import aff4
from grr.lib import rdfvalue


class MostActiveUsers(statistics.PieChart):
  category = "/Server/User Breakdown/ 7 Day"
  description = "Active User actions in the last week."

  def Layout(self, request, response):
    """Filter the last week of user actions."""
    try:
      # TODO(user): Replace with Duration().
      now = int(rdfvalue.RDFDatetime().Now())
      fd = aff4.FACTORY.Open("aff4:/audit/log", aff4_type="VersionedCollection",
                             token=request.token)

      counts = {}
      for event in fd.GenerateItems(
          timestamp=(now - 7 * 24 * 60 * 60 * 1000000, now)):
        counts.setdefault(event.user, 0)
        counts[event.user] += 1

      self.graph = rdfvalue.Graph(title="User activity breakdown.")
      self.data = []
      for user, count in counts.items():
        if user not in self.SYSTEM_USERS:
          self.graph.Append(label=user, y_value=count)
          self.data.append(dict(label=user, data=count))
    except IOError:
      pass
    return super(MostActiveUsers, self).Layout(request, response)


class StackChart(statistics.Report):
  """Display category data in stacked histograms."""

  layout_template = renderers.Template("""
<div class="padded">
{% if this.data %}
  <h3>{{this.title|escape}}</h3>
  <div>
  {{this.description|escape}}
  </div>
  <div id="hover">Hover to show exact numbers.</div>
  <div id="{{unique|escape}}" class="grr_graph"></div>
  <script>

  var specs = {{this.data|safe}};

  $("#{{unique|escapejs}}").resize(function () {
    $("#{{unique|escapejs}}").html("");
    $.plot($("#{{unique|escapejs}}"), specs, {
      series: {
        stack: true,
        bars: {
          show: true,
          barWidth: 0.6,
        },
        label: {
          show: true,
          radius: 0.5,
        },
        background: { opacity: 0.8 },
      },
      grid: {
        hoverable: true,
        clickable: true
      },
    });
  });

  $("#{{unique|escapejs}}").bind("plothover", function(event, pos, obj) {
    if (obj) {
      grr.test_obj = obj;
      $("#hover").html(
        '<span style="font-weight: bold; color: ' +
        obj.series.color + '"> <b>' + obj.series.label + "</b>: " +
        (obj.datapoint[1] - obj.datapoint[2]) + '</span>');
    }
  });

  $("#{{unique|escapejs}}").resize();
  </script>
{% else %}
  <h3>No data Available</h3>
{% endif %}
</div>
""")


class UserActivity(StackChart):
  """Display user activity by week."""
  category = "/Server/User Breakdown/Activity"
  description = "Number of flows ran by each user over the last few weeks."
  WEEKS = 10

  def Layout(self, request, response):
    """Filter the last week of user actions."""
    try:
      # TODO(user): Replace with Duration().
      now = int(rdfvalue.RDFDatetime().Now())
      week_duration = 7 * 24 * 60 * 60 * 1000000

      fd = aff4.FACTORY.Open("aff4:/audit/log", aff4_type="VersionedCollection",
                             token=request.token)

      self.user_activity = {}

      for week in range(self.WEEKS):
        start = now - week * week_duration

        for event in fd.GenerateItems(timestamp=(start, start + week_duration)):
          self.weekly_activity = self.user_activity.setdefault(
              event.user, [[x, 0] for x in range(-self.WEEKS, 0, 1)])
          self.weekly_activity[-week][1] += 1

      self.data = []
      for user, data in self.user_activity.items():
        if user not in self.SYSTEM_USERS:
          self.data.append(dict(label=user, data=data))

      self.data = renderers.JsonDumpForScriptContext(self.data)

    except IOError:
      pass

    return super(UserActivity, self).Layout(request, response)


class SystemFlows(statistics.Report, renderers.TableRenderer):
  """Count last week's system-created flows by type."""
  category = "/Server/Flows/System/  7 days"
  title = "7-Day System Flow Count"
  description = ("Flows launched by GRR crons and workers over the last 7 days"
                 " grouped by type.")
  layout_template = renderers.Template("""
<div class="padded">
  <h3>{{this.title|escape}}</h3>
  <div>
  {{this.description|escape}}
  </div>
</div>
""") + renderers.TableRenderer.layout_template
  time_offset = rdfvalue.Duration("7d")

  def __init__(self, **kwargs):
    super(SystemFlows, self).__init__(**kwargs)
    self.AddColumn(semantic.RDFValueColumn("Flow Name"))
    self.AddColumn(semantic.RDFValueColumn("Run Count"))
    self.AddColumn(semantic.RDFValueColumn("Most Run By"))

  def UserFilter(self, username):
    return username in self.SYSTEM_USERS

  def BuildTable(self, start_row, end_row, request):
    # TODO(user): move the calculation to a cronjob and store results in
    # AFF4.
    try:
      now = rdfvalue.RDFDatetime().Now()
      start = now - self.time_offset
      fd = aff4.FACTORY.Open("aff4:/audit/log", aff4_type="VersionedCollection",
                             token=request.token)

      # Store run count total and per-user
      counts = {}
      for event in fd.GenerateItems(timestamp=(start.AsMicroSecondsFromEpoch(),
                                               now.AsMicroSecondsFromEpoch())):
        if (event.action == rdfvalue.AuditEvent.Action.RUN_FLOW and
            self.UserFilter(event.user)):
          counts.setdefault(event.flow_name, {"total": 0, event.user: 0})
          counts[event.flow_name]["total"] += 1
          counts[event.flow_name].setdefault(event.user, 0)
          counts[event.flow_name][event.user] += 1

      for flow, countdict in sorted(counts.iteritems(),
                                    key=lambda x: x[1]["total"],
                                    reverse=True):
        total_count = countdict["total"]
        countdict.pop("total")
        topusercounts = sorted(countdict.iteritems(),
                               key=operator.itemgetter(1), reverse=True)[0:3]
        topusers = ", ".join("%s (%s)" % (user, count) for user, count in
                             topusercounts)
        self.AddRow({"Flow Name": flow, "Run Count": total_count,
                     "Most Run By": topusers})
    except IOError:
      pass


class SystemFlows30(SystemFlows):
  """Count last month's system-created flows by type."""
  category = "/Server/Flows/System/ 30 days"
  title = "30-Day System Flow Count"
  description = ("Flows launched by GRR crons and workers over the last 30 days"
                 " grouped by type.")
  time_offset = rdfvalue.Duration("30d")


class UserFlows(SystemFlows):
  """Count last week's user-created flows by type."""
  category = "/Server/Flows/User/  7 days"
  title = "7-Day User Flow Count"
  description = ("Flows launched by GRR users over the last 7 days"
                 " grouped by type.")

  def UserFilter(self, username):
    return username not in self.SYSTEM_USERS


class UserFlows30(UserFlows):
  """Count last month's user-created flows by type."""
  category = "/Server/Flows/User/ 30 days"
  title = "30-Day User Flow Count"
  description = ("Flows launched by GRR users over the last 30 days"
                 " grouped by type.")
  time_offset = rdfvalue.Duration("30d")


class ClientActivity(StackChart):
  """Display client activity by week."""
  category = "/Server/Clients/Activity"
  description = ("Number of flows issued against each client over the "
                 "last few weeks.")

  WEEKS = 10

  def Layout(self, request, response):
    """Filter the last week of flows."""
    try:
      # TODO(user): Replace with Duration().
      now = int(rdfvalue.RDFDatetime().Now())
      week_duration = 7 * 24 * 60 * 60 * 1000000

      fd = aff4.FACTORY.Open("aff4:/audit/log", aff4_type="VersionedCollection",
                             token=request.token)

      self.client_activity = {}

      for week in range(self.WEEKS):
        start = now - week * week_duration

        for event in fd.GenerateItems(timestamp=(start, start + week_duration)):
          self.weekly_activity = self.client_activity.setdefault(
              event.client, [[x, 0] for x in range(-self.WEEKS, 0, 1)])
          self.weekly_activity[-week][1] += 1

      self.data = []
      for client, data in self.client_activity.items():
        if client:
          self.data.append(dict(label=str(client), data=data))

      self.data = renderers.JsonDumpForScriptContext(self.data)

    except IOError:
      pass

    return super(ClientActivity, self).Layout(request, response)


class AuditTable(statistics.Report, renderers.TableRenderer):
  """Parent class for audit event tabular reports."""
  layout_template = renderers.Template("""
<div class="padded">
  <h3>{{this.title|escape}}</h3>
</div>
""") + renderers.TableRenderer.layout_template
  time_offset = rdfvalue.Duration("7d")
  column_map = {"Timestamp": "timestamp", "Action": "action", "User": "user",
                "Client": "client", "Flow Name": "flow_name", "URN": "urn",
                "Description": "description"}

  # To be set by subclass
  TYPES = []

  def __init__(self, **kwargs):
    super(AuditTable, self).__init__(**kwargs)
    for column_name in sorted(self.column_map):
      self.AddColumn(semantic.RDFValueColumn(column_name))

  def BuildTable(self, start_row, end_row, request):
    try:
      now = rdfvalue.RDFDatetime().Now()
      start = now - self.time_offset
      fd = aff4.FACTORY.Open("aff4:/audit/log", aff4_type="VersionedCollection",
                             token=request.token)

      rows = []
      for event in fd.GenerateItems(timestamp=(start.AsMicroSecondsFromEpoch(),
                                               now.AsMicroSecondsFromEpoch())):
        if event.action in self.TYPES:
          row_dict = {}
          for column_name, attribute in self.column_map.iteritems():
            row_dict[column_name] = event.Get(attribute)
          rows.append(row_dict)

      for row in sorted(rows, key=lambda x: x["Timestamp"]):
        self.AddRow(row)

    except IOError:
      pass


class ClientApprovals(AuditTable):
  """Last week's client approvals."""
  category = "/Server/Approvals/Clients/  7 days"
  title = "Client approval requests and grants for the last 7 days"
  column_map = {"Timestamp": "timestamp", "Approval Type": "action", "User":
                "user", "Client": "client", "Reason": "description"}
  TYPES = [rdfvalue.AuditEvent.Action.CLIENT_APPROVAL_BREAK_GLASS_REQUEST,
           rdfvalue.AuditEvent.Action.CLIENT_APPROVAL_GRANT,
           rdfvalue.AuditEvent.Action.CLIENT_APPROVAL_REQUEST]


class ClientApprovals30(ClientApprovals):
  """Last month's client approvals."""
  category = "/Server/Approvals/Clients/ 30 days"
  title = "Client approval requests and grants for the last 30 days"
  time_offset = rdfvalue.Duration("30d")


class HuntApprovals(AuditTable):
  """Last week's hunt approvals."""
  category = "/Server/Approvals/Hunts/  7 days"
  title = "Hunt approval requests and grants for the last 7 days"
  column_map = {"Timestamp": "timestamp", "Approval Type": "action", "User":
                "user", "URN": "urn", "Reason": "description"}
  TYPES = [rdfvalue.AuditEvent.Action.HUNT_APPROVAL_GRANT,
           rdfvalue.AuditEvent.Action.HUNT_APPROVAL_REQUEST]


class HuntApprovals30(HuntApprovals):
  """Last month's hunt approvals."""
  category = "/Server/Approvals/Hunts/ 30 days"
  title = "Hunt approval requests and grants for the last 30 days"
  time_offset = rdfvalue.Duration("30d")


class CronApprovals(HuntApprovals):
  """Last week's cron approvals."""
  category = "/Server/Approvals/Crons/  7 days"
  title = "Cron approval requests and grants for the last 7 days"
  TYPES = [rdfvalue.AuditEvent.Action.CRON_APPROVAL_GRANT,
           rdfvalue.AuditEvent.Action.CRON_APPROVAL_REQUEST]


class CronApprovals30(CronApprovals):
  """Last month's cron approvals."""
  category = "/Server/Approvals/Crons/ 30 days"
  title = "Cron approval requests and grants for the last 30 days"
  time_offset = rdfvalue.Duration("30d")


class HuntActions(AuditTable):
  """Last week's hunt actions."""
  category = "/Server/Hunts/  7 days"
  title = "Hunt management actions for the last 7 days"
  column_map = {"Timestamp": "timestamp", "Action": "action",
                "User": "user", "Flow Name": "flow_name", "URN": "urn",
                "Description": "description"}

  TYPES = [rdfvalue.AuditEvent.Action.HUNT_CREATED,
           rdfvalue.AuditEvent.Action.HUNT_MODIFIED,
           rdfvalue.AuditEvent.Action.HUNT_PAUSED,
           rdfvalue.AuditEvent.Action.HUNT_STARTED,
           rdfvalue.AuditEvent.Action.HUNT_STOPPED]


class HuntActions30(HuntActions):
  """Last month's hunt actions."""
  category = "/Server/Hunts/ 30 days"
  title = "Hunt management actions for the last 30 days"
  time_offset = rdfvalue.Duration("30d")
