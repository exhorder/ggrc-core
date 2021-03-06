# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Module with CalendarEventBuilder class."""

from collections import defaultdict
from sqlalchemy.orm import load_only
from sqlalchemy import orm

from ggrc import db
from ggrc import settings
from ggrc.models import all_models
from ggrc.gcalendar import utils
from ggrc.utils import benchmark


# pylint: disable=too-few-public-methods
class CalendarEventBuilder(object):
  """Class with builder methods for CalendarEvent model."""

  TASK_DESCRIPTION_HEADER = u"You have due tasks for today.\n"
  TASK_DESCRIPTION_SUMMARY = (
      u"Please click on the link below to review "
      u"and take action on your task(s) due today.\n"
      u"<a href='{link}'>Link</a>")
  TASK_TITLE_TEMPLATE = u"{prefix}Your tasks are due today"

  def __init__(self):
    """Initialize CalendarEventBuilder."""
    self.task_mappings = defaultdict(set)
    self.event_mappings = defaultdict(set)
    self.tasks = []
    self.title_prefix = ""
    if settings.NOTIFICATION_PREFIX:
      self.title_prefix = "[{}] ".format(settings.NOTIFICATION_PREFIX)

  def build_cycle_tasks(self):
    """Builds CalendarEvents based on CycleTaskGroupObjectTasks."""
    with benchmark("Generating of events for cycle tasks."):
      self._preload_data()
      self._generate_events()
      self._generate_event_descriptions()
      db.session.commit()

  def _preload_data(self):
    """Preload data for Calendar Event generation."""
    self.task_mappings, self.event_mappings = utils.get_related_mapping(
        left=all_models.CycleTaskGroupObjectTask,
        right=all_models.CalendarEvent
    )
    self.tasks = all_models.CycleTaskGroupObjectTask.query.options(
        orm.joinedload("cycle").load_only(
            "workflow_id",
        )
        .joinedload("workflow").load_only(
            "unit",
            "recurrences",
            "next_cycle_start_date",
        ),
        load_only(
            all_models.CycleTaskGroupObjectTask.id,
            all_models.CycleTaskGroupObjectTask.end_date,
            all_models.CycleTaskGroupObjectTask.status,
            all_models.CycleTaskGroupObjectTask.title,
            all_models.CycleTaskGroupObjectTask.verified_date,
        ),
    ).all()

  def _generate_events(self):
    """Generates Calendar Events."""
    for task in self.tasks:
      self._generate_events_for_task(task)
    db.session.flush()

  def _generate_events_for_task(self, task):
    """Generates CalendarEvents for CycleTaskGroupObjectTask."""
    events_ids = set()
    if task.id in self.task_mappings:
      events_ids = self.task_mappings[task.id].copy()

    if self._should_create_event_for(task):
      for person_id in self._get_task_persons_ids_to_notify(task):
        event = utils.get_event_by_date_and_attendee(
            attendee_id=person_id,
            due_date=task.end_date
        )
        if not event:
          self._create_event_with_relationship(task, person_id)
        else:
          self._create_event_relationship(task, event)
          events_ids.discard(event.id)
    for event_id in events_ids:
      self._delete_event_relationship(event_id, task.id)

  @staticmethod
  def _get_task_persons_ids_to_notify(task):
    """Returns set of person ids for which calendar event should be created."""
    roles_to_notify = [u"Task Assignees", u"Task Secondary Assignees"]
    person_ids = []
    for role in roles_to_notify:
      person_ids.extend(task.get_person_ids_for_rolename(role))
    return set(person_ids)

  def _delete_event_relationship(self, event_id, task_id):
    """Deletes calendar event relationship to task."""
    relationship = utils.get_relationship(
        left_id=event_id,
        left_model_name="CalendarEvent",
        right_id=task_id,
        right_model_name="CycleTaskGroupObjectTask",
    )
    if relationship:
      db.session.delete(relationship)
      self.task_mappings[task_id].discard(event_id)
      self.event_mappings[event_id].discard(task_id)

  def _create_event_with_relationship(self, task, person_id):
    """Creates calendar event and relationship based on task and person id."""
    event = all_models.CalendarEvent(
        due_date=task.end_date,
        attendee_id=person_id,
        title=self.TASK_TITLE_TEMPLATE.format(prefix=self.title_prefix),
        modified_by_id=person_id,
    )
    db.session.add(event)
    db.session.add(all_models.Relationship(
        source=task,
        destination=event,
    ))
    db.session.flush()
    self.task_mappings[task.id].add(event.id)
    self.event_mappings[event.id].add(task.id)
    return event

  def _create_event_relationship(self, task, event):
    """Creates event relationship is it is not exists."""
    relationship = utils.get_relationship(
        left_id=event.id,
        left_model_name="CalendarEvent",
        right_id=task.id,
        right_model_name="CycleTaskGroupObjectTask",
    )
    if not relationship:
      db.session.add(all_models.Relationship(
          source=task,
          destination=event,
      ))
      self.task_mappings[task.id].add(event.id)
      self.event_mappings[event.id].add(task.id)

  @staticmethod
  def _should_create_event_for(task):
    """Determines should we create a Calendar Event for the task or not.

    Calendar events should NOT be created for:
    - deprecated cycle tasks.
    - verified cycle tasks (in case it has Verification flow).
    - finished cycle tasks (in case it has no Verification flow).
    - 'in progress' cycle tasks within a cycle that was ended
      (tasks are stored at 'History' tab).
    - overdue cycle tasks.
    - cycle tasks of the archived workflows.
    """

    conditions = [
        task.status in [task.DEPRECATED, task.VERIFIED],
        task.status == task.FINISHED and not task.is_verification_needed,
        task.is_in_history,
        task.is_overdue,
        task.workflow.workflow_archived,
    ]
    return not any(conditions)

  def _generate_event_descriptions(self):
    """Generates CalendarEvents descriptions."""
    events = db.session.query(all_models.CalendarEvent).options(
        load_only(
            all_models.CalendarEvent.id,
            all_models.CalendarEvent.description,
        )
    ).all()
    for event in events:
      if event.id not in self.event_mappings:
        continue
      task_ids = self.event_mappings[event.id]
      self._generate_description_for_event(event, task_ids)

  def _generate_description_for_event(self, event, task_ids):
    """Generates CalendarEvent descriptions based on tasks."""
    titles = ["- {}".format(task.title) for task in self.tasks
              if task.id in task_ids]
    event.description = (
        self.TASK_DESCRIPTION_HEADER +
        "\n".join(titles) + "\n" + self.TASK_DESCRIPTION_SUMMARY.format(
            link=utils.get_active_cycle_tasks_url(
                due_date=event.due_date.strftime('%m/%d/%Y')
            )
        )
    )
