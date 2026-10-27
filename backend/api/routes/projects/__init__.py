"""
Project management API routes package.

Modules:
- common: Shared schemas, imports, helpers
- crud: Project CRUD
- members: Member management
- tasks: Task CRUD + kanban
- milestones: Milestone CRUD
- time_logs: Effort tracking
- analytics: Project analytics
"""
from fastapi import APIRouter

router = APIRouter()

# Import handlers
from .crud import list_projects, create_project, get_project, update_project, delete_project
from .members import list_members, add_member, update_member, remove_member
from .tasks import list_tasks, create_task, get_task, update_task, delete_task, get_task_kanban, bulk_move_tasks, get_all_tasks, get_subtasks
from .milestones import list_milestones, create_milestone, update_milestone, delete_milestone
from .time_logs import create_time_log, list_task_time_logs, delete_time_log, get_project_effort
from .analytics import get_projects_overview, get_resource_allocation, get_project_analytics
from .custom_fields import list_custom_fields, create_custom_field, update_custom_field, delete_custom_field, get_task_field_values, set_task_field_value
from .statuses import list_statuses, create_status, update_status, delete_status, reorder_statuses
from .comments import list_comments, create_comment, update_comment, delete_comment
from .attachments import list_attachments, upload_attachment, download_attachment, delete_attachment
from .ai_tasks import ai_parse_plan, ai_create_tasks
from .triggers import test_trigger

# Register routes — specific paths before parameterized ones

# Analytics (before /{project_id})
router.add_api_route("/analytics/overview", get_projects_overview, methods=["GET"], tags=["project-analytics"])
router.add_api_route("/analytics/resources", get_resource_allocation, methods=["GET"], tags=["project-analytics"])

# All tasks across projects (before /{project_id})
router.add_api_route("/all-tasks", get_all_tasks, methods=["GET"], tags=["project-tasks"])

# AI task creation (before /{project_id} catch-all)
router.add_api_route("/{project_id}/ai/parse-plan", ai_parse_plan, methods=["POST"], tags=["project-ai"])
router.add_api_route("/{project_id}/ai/create-tasks", ai_create_tasks, methods=["POST"], tags=["project-ai"])
router.add_api_route("/{project_id}/trigger-test", test_trigger, methods=["POST"], tags=["project-triggers"])

# CRUD: list and create (root path)
router.add_api_route("", list_projects, methods=["GET"], tags=["projects"])
router.add_api_route("", create_project, methods=["POST"], status_code=201, tags=["projects"])

# Single project
router.add_api_route("/{project_id}", get_project, methods=["GET"], tags=["projects"])
router.add_api_route("/{project_id}", update_project, methods=["PUT"], tags=["projects"])
router.add_api_route("/{project_id}", delete_project, methods=["DELETE"], status_code=204, tags=["projects"])

# Project analytics
router.add_api_route("/{project_id}/analytics", get_project_analytics, methods=["GET"], tags=["project-analytics"])

# Members
router.add_api_route("/{project_id}/members", list_members, methods=["GET"], tags=["project-members"])
router.add_api_route("/{project_id}/members", add_member, methods=["POST"], status_code=201, tags=["project-members"])
router.add_api_route("/{project_id}/members/{user_id}", update_member, methods=["PUT"], tags=["project-members"])
router.add_api_route("/{project_id}/members/{user_id}", remove_member, methods=["DELETE"], status_code=204, tags=["project-members"])

# Milestones
router.add_api_route("/{project_id}/milestones", list_milestones, methods=["GET"], tags=["project-milestones"])
router.add_api_route("/{project_id}/milestones", create_milestone, methods=["POST"], status_code=201, tags=["project-milestones"])
router.add_api_route("/{project_id}/milestones/{milestone_id}", update_milestone, methods=["PUT"], tags=["project-milestones"])
router.add_api_route("/{project_id}/milestones/{milestone_id}", delete_milestone, methods=["DELETE"], status_code=204, tags=["project-milestones"])

# Tasks
router.add_api_route("/{project_id}/tasks", list_tasks, methods=["GET"], tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks", create_task, methods=["POST"], status_code=201, tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks/kanban", get_task_kanban, methods=["GET"], tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks/move", bulk_move_tasks, methods=["POST"], tags=["project-tasks"])
# Comments
router.add_api_route("/{project_id}/tasks/{task_id}/comments", list_comments, methods=["GET"], tags=["project-comments"])
router.add_api_route("/{project_id}/tasks/{task_id}/comments", create_comment, methods=["POST"], status_code=201, tags=["project-comments"])
router.add_api_route("/{project_id}/tasks/{task_id}/comments/{comment_id}", update_comment, methods=["PUT"], tags=["project-comments"])
router.add_api_route("/{project_id}/tasks/{task_id}/comments/{comment_id}", delete_comment, methods=["DELETE"], status_code=204, tags=["project-comments"])

# Attachments
router.add_api_route("/{project_id}/tasks/{task_id}/attachments", list_attachments, methods=["GET"], tags=["project-attachments"])
router.add_api_route("/{project_id}/tasks/{task_id}/attachments", upload_attachment, methods=["POST"], status_code=201, tags=["project-attachments"])
router.add_api_route("/{project_id}/tasks/{task_id}/attachments/{attachment_id}", download_attachment, methods=["GET"], tags=["project-attachments"])
# Алиас с /download — вкладка «Файлы» ссылается на этот путь.
router.add_api_route("/{project_id}/tasks/{task_id}/attachments/{attachment_id}/download", download_attachment, methods=["GET"], tags=["project-attachments"])
router.add_api_route("/{project_id}/tasks/{task_id}/attachments/{attachment_id}", delete_attachment, methods=["DELETE"], status_code=204, tags=["project-attachments"])

router.add_api_route("/{project_id}/tasks/{task_id}", get_task, methods=["GET"], tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks/{task_id}", update_task, methods=["PUT"], tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks/{task_id}", delete_task, methods=["DELETE"], status_code=204, tags=["project-tasks"])
router.add_api_route("/{project_id}/tasks/{task_id}/subtasks", get_subtasks, methods=["GET"], tags=["project-tasks"])

# Time logs
router.add_api_route("/{project_id}/tasks/{task_id}/time-logs", list_task_time_logs, methods=["GET"], tags=["project-time-logs"])
router.add_api_route("/{project_id}/tasks/{task_id}/time-logs", create_time_log, methods=["POST"], status_code=201, tags=["project-time-logs"])
router.add_api_route("/{project_id}/tasks/{task_id}/time-logs/{log_id}", delete_time_log, methods=["DELETE"], status_code=204, tags=["project-time-logs"])

# Project effort summary
router.add_api_route("/{project_id}/effort", get_project_effort, methods=["GET"], tags=["project-time-logs"])

# Custom fields
router.add_api_route("/{project_id}/custom-fields", list_custom_fields, methods=["GET"], tags=["project-custom-fields"])
router.add_api_route("/{project_id}/custom-fields", create_custom_field, methods=["POST"], status_code=201, tags=["project-custom-fields"])
router.add_api_route("/{project_id}/custom-fields/{field_id}", update_custom_field, methods=["PUT"], tags=["project-custom-fields"])
router.add_api_route("/{project_id}/custom-fields/{field_id}", delete_custom_field, methods=["DELETE"], status_code=204, tags=["project-custom-fields"])
router.add_api_route("/{project_id}/tasks/{task_id}/field-values", get_task_field_values, methods=["GET"], tags=["project-custom-fields"])
router.add_api_route("/{project_id}/tasks/{task_id}/field-values/{field_id}", set_task_field_value, methods=["PUT"], tags=["project-custom-fields"])

# Task statuses
router.add_api_route("/{project_id}/statuses", list_statuses, methods=["GET"], tags=["project-statuses"])
router.add_api_route("/{project_id}/statuses", create_status, methods=["POST"], status_code=201, tags=["project-statuses"])
router.add_api_route("/{project_id}/statuses/reorder", reorder_statuses, methods=["PUT"], tags=["project-statuses"])
router.add_api_route("/{project_id}/statuses/{status_id}", update_status, methods=["PUT"], tags=["project-statuses"])
router.add_api_route("/{project_id}/statuses/{status_id}", delete_status, methods=["DELETE"], status_code=204, tags=["project-statuses"])
