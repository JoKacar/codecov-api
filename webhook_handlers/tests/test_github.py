import uuid
import pytest

from unittest.mock import patch, call

from rest_framework.test import APITestCase
from rest_framework.reverse import reverse
from rest_framework import status

from core.tests.factories import RepositoryFactory, BranchFactory, CommitFactory, PullFactory
from core.models import Repository
from codecov_auth.models import Owner
from codecov_auth.tests.factories import OwnerFactory

from webhook_handlers.constants import GitHubHTTPHeaders, GitHubWebhookEvents, WebhookHandlerErrorMessages


class GithubWebhookHandlerTests(APITestCase):
    def _post_event_data(self, event, data={}):
        return self.client.post(
            reverse("github-webhook"),
            **{
                GitHubHTTPHeaders.EVENT: event,
                GitHubHTTPHeaders.DELIVERY_TOKEN: uuid.UUID(int=5),
                GitHubHTTPHeaders.SIGNATURE: 0
            },
            data=data,
            format="json"
        )

    def setUp(self):
        self.repo = RepositoryFactory(
            author=OwnerFactory(service="github"),
            service_id=12345,
            active=True
        )

    def test_ping_returns_pong_and_200(self):
        response = self._post_event_data(event=GitHubWebhookEvents.PING)
        assert response.status_code == status.HTTP_200_OK

    def test_repository_publicized_sets_activated_false_and_private_false(self):
        self.repo.private = True
        self.repo.activated = True

        self.repo.save()

        response = self._post_event_data(
            event=GitHubWebhookEvents.REPOSITORY,
            data={
                "action": "publicized",
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK

        self.repo.refresh_from_db()

        assert self.repo.private == False
        assert self.repo.activated == False

    def test_repository_privatized_sets_private_true(self):
        self.repo.private = False
        self.repo.save()

        response = self._post_event_data(
            event=GitHubWebhookEvents.REPOSITORY,
            data={
                "action": "privatized",
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK

        self.repo.refresh_from_db()

        assert self.repo.private == True

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.delete_repo_files', lambda _: None)
    def test_repository_deleted_deletes_repo(self):
        repository_id = self.repo.repoid

        response = self._post_event_data(
            event=GitHubWebhookEvents.REPOSITORY,
            data={
                "action": "deleted",
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert not Repository.objects.filter(repoid=repository_id).exists()

    @patch('services.archive.ArchiveService.create_root_storage', lambda _: None)
    @patch('services.archive.ArchiveService.delete_repo_files')
    def test_repository_delete_deletes_archive_data(self, delete_files_mock):
        response = self._post_event_data(
            event=GitHubWebhookEvents.REPOSITORY,
            data={
                "action": "deleted",
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK
        delete_files_mock.assert_called_once()

    def test_delete_event_deletes_branch(self):
        branch = BranchFactory(repository=self.repo)

        response = self._post_event_data(
            event=GitHubWebhookEvents.DELETE,
            data={
                "ref": "refs/heads/" + branch.name,
                "ref_type": "branch",
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert not self.repo.branches.filter(name=branch.name).exists()

    def test_public_sets_repo_private_false_and_activated_false(self):
        self.repo.private = True
        self.repo.activated = True
        self.repo.save()

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUBLIC,
            data={
                "repository": {
                    "id": self.repo.service_id
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK
        self.repo.refresh_from_db()
        assert not self.repo.private
        assert not self.repo.activated

    @patch('redis.Redis.sismember', lambda x, y, z: False)
    def test_push_updates_only_unmerged_commits_with_branch_name(self):
        commit1 = CommitFactory(merged=False, repository=self.repo)
        commit2 = CommitFactory(merged=False, repository=self.repo)

        merged_branch_name = "merged"
        unmerged_branch_name = "unmerged"

        merged_commit = CommitFactory(merged=True, repository=self.repo, branch=merged_branch_name)

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUSH,
            data={
                "ref": "refs/heads/" + unmerged_branch_name,
                "repository": {
                    "id": self.repo.service_id
                },
                "commits": [
                    {"id": commit1.commitid, "message": commit1.message},
                    {"id": commit2.commitid, "message": commit2.message},
                    {"id": merged_commit.commitid, "message": merged_commit.message}
                ]
            }
        )

        commit1.refresh_from_db()
        commit2.refresh_from_db()
        merged_commit.refresh_from_db()

        assert commit1.branch == unmerged_branch_name
        assert commit2.branch == unmerged_branch_name

        assert merged_commit.branch == merged_branch_name

    def test_push_exits_early_with_200_if_repo_not_active(self):
        self.repo.active = False
        self.repo.save()
        unmerged_commit = CommitFactory(repository=self.repo, merged=False)
        branch_name = "new-branch-name"

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUSH,
            data={
                "ref": "refs/heads/" + branch_name,
                "repository": {
                    "id": self.repo.service_id
                },
                "commits": [
                    {"id": unmerged_commit.commitid, "message": unmerged_commit.message}
                ]
            }
        )

        assert response.status_code == status.HTTP_200_OK

        unmerged_commit.refresh_from_db()
        assert unmerged_commit.branch != branch_name

    @patch('redis.Redis.sismember', lambda x, y, z: True)
    @patch('services.task.TaskService.status_set_pending')
    def test_push_triggers_set_pending_task_on_most_recent_commit(self, set_pending_mock):
        commit1 = CommitFactory(merged=False, repository=self.repo)
        commit2 = CommitFactory(merged=False, repository=self.repo)
        unmerged_branch_name = "unmerged"

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUSH,
            data={
                "ref": "refs/heads/" + unmerged_branch_name,
                "repository": {
                    "id": self.repo.service_id
                },
                "commits": [
                    {"id": commit1.commitid, "message": commit1.message},
                    {"id": commit2.commitid, "message": commit2.message}
                ]
            }
        )

        set_pending_mock.assert_called_once_with(
            repoid=self.repo.repoid,
            commitid=commit2.commitid,
            branch=unmerged_branch_name,
            on_a_pull_request=False
        )

    @patch('redis.Redis.sismember', lambda x, y, z: False)
    @patch('services.task.TaskService.status_set_pending')
    def test_push_doesnt_trigger_task_if_repo_not_part_of_beta_set(self, set_pending_mock):
        commit1 = CommitFactory(merged=False, repository=self.repo)
        unmerged_branch_name = "unmerged"

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUSH,
            data={
                "ref": "refs/heads/" + "derp",
                "repository": {
                    "id": self.repo.service_id
                },
                "commits": [
                    {"id": commit1.commitid, "message": commit1.message}
                ]
            }
        )

        set_pending_mock.assert_not_called()

    @patch('redis.Redis.sismember', lambda x, y, z: True)
    @patch('services.task.TaskService.status_set_pending')
    def test_push_doesnt_trigger_task_if_ci_skipped(self, set_pending_mock):
        commit1 = CommitFactory(merged=False, repository=self.repo, message="[ci skip]")
        unmerged_branch_name = "unmerged"

        response = self._post_event_data(
            event=GitHubWebhookEvents.PUSH,
            data={
                "ref": "refs/heads/" + "derp",
                "repository": {
                    "id": self.repo.service_id
                },
                "commits": [
                    {"id": commit1.commitid, "message": commit1.message}
                ]
            }
        )

        assert response.data == "CI Skipped"
        set_pending_mock.assert_not_called()

    def test_status_exits_early_if_repo_not_active(self):
        self.repo.active = False
        self.repo.save()

        response = self._post_event_data(
            event=GitHubWebhookEvents.STATUS,
            data={
                "repository": {
                    "id": self.repo.service_id
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == WebhookHandlerErrorMessages.SKIP_NOT_ACTIVE

    def test_status_exits_early_for_codecov_statuses(self):
        response = self._post_event_data(
            event=GitHubWebhookEvents.STATUS,
            data={
                "context": "codecov/",
                "repository": {
                    "id": self.repo.service_id
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == WebhookHandlerErrorMessages.SKIP_CODECOV_STATUS

    def test_status_exits_early_for_pending_statuses(self):
        response = self._post_event_data(
            event=GitHubWebhookEvents.STATUS,
            data={
                "state": "pending",
                "repository": {
                    "id": self.repo.service_id
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == WebhookHandlerErrorMessages.SKIP_PENDING_STATUSES

    def test_status_exits_early_if_commit_not_complete(self):
        response = self._post_event_data(
            event=GitHubWebhookEvents.STATUS,
            data={
                "repository": {
                    "id": self.repo.service_id
                },
                "sha": CommitFactory(repository=self.repo, state="pending").commitid
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == WebhookHandlerErrorMessages.SKIP_PROCESSING

    @patch('services.task.TaskService.notify')
    def test_status_triggers_notify_task(self, notify_mock):
        commit = CommitFactory(repository=self.repo)
        response = self._post_event_data(
            event=GitHubWebhookEvents.STATUS,
            data={
                "repository": {
                    "id": self.repo.service_id
                },
                "sha": commit.commitid
            }
        )

        assert response.status_code == status.HTTP_200_OK
        notify_mock.assert_called_once_with(repoid=self.repo.repoid, commitid=commit.commitid)

    def test_pull_request_exits_early_if_repo_not_active(self):
        self.repo.active = False
        self.repo.save()

        response = self._post_event_data(
            event=GitHubWebhookEvents.PULL_REQUEST,
            data={
                "repository": {
                    "id": self.repo.service_id
                },
            }
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == WebhookHandlerErrorMessages.SKIP_NOT_ACTIVE

    @pytest.mark.xfail
    def test_pull_request_triggers_pulls_sync_task_for_valid_actions(self):
        assert False

    def test_pull_request_updates_title_if_edited(self):
        pull = PullFactory(repository=self.repo)
        new_title = "brand new dang title"
        response = self._post_event_data(
            event=GitHubWebhookEvents.PULL_REQUEST,
            data={
                "repository": {
                    "id": self.repo.service_id
                },
                "action": "edited",
                "number": pull.pullid,
                "pull_request": {
                    "title": new_title,
                }
            }
        )

        assert response.status_code == status.HTTP_200_OK

        pull.refresh_from_db()
        assert pull.title == new_title

    @patch('services.task.TaskService.refresh', lambda self, ownerid, username, sync_teams, sync_repos, using_integration: None)
    def test_installation_events_creates_new_owner_if_dne(self):
        username, service_id = 'newuser', 123456

        for event in [GitHubWebhookEvents.INSTALLATION, GitHubWebhookEvents.INSTALLATION_REPOSITORIES]:
            response = self._post_event_data(
                event=event,
                data={
                    "installation": {
                        "id": 4,
                        "account": {
                            "id": service_id,
                            "login": username
                        }
                    }
                }
            )

            owner = Owner.objects.filter(
                service="github",
                service_id=service_id,
                username=username
            )

            assert owner.exists()

            # clear to check next event also creates
            owner.delete()

    def test_installation_events_with_deleted_action_nulls_values(self):
        # Should set integration_id to null for owner,
        # and set using_integration=False and bot=null for repos
        owner = OwnerFactory()
        repo1 = RepositoryFactory(author=owner)
        repo2 = RepositoryFactory(author=owner)

        for event in [GitHubWebhookEvents.INSTALLATION, GitHubWebhookEvents.INSTALLATION_REPOSITORIES]:
            owner.integration_id = 12
            owner.save()

            repo1.using_integration, repo2.using_integration = True, True
            repo1.bot, repo2.bot = owner, owner

            repo1.save()
            repo2.save()

            response = self._post_event_data(
                event=event,
                data={
                    "installation": {
                        "account": {
                            "id": owner.service_id,
                            "login": owner.username
                        }
                    },
                    "action": "deleted"
                }
            )

            owner.refresh_from_db()
            repo1.refresh_from_db()
            repo2.refresh_from_db()

            assert owner.integration_id == None
            assert repo1.using_integration == False
            assert repo2.using_integration == False

            assert repo1.bot == None
            assert repo2.bot == None

    @patch('services.task.TaskService.refresh', lambda self, ownerid, username, sync_teams, sync_repos, using_integration: None)
    def test_installation_events_with_other_actions_sets_owner_itegration_id_if_none(self):
        integration_id = 44
        owner = OwnerFactory()

        for event in [GitHubWebhookEvents.INSTALLATION, GitHubWebhookEvents.INSTALLATION_REPOSITORIES]:
            owner.integration_id = None
            owner.save()

            response = self._post_event_data(
                event=event,
                data={
                    "installation": {
                        "id": integration_id,
                        "account": {
                            "id": owner.service_id,
                            "login": owner.username
                        }
                    },
                    "action": "added"
                }
            )

            owner.refresh_from_db()

            assert owner.integration_id == integration_id

    @patch('services.task.TaskService.refresh')
    def test_installation_events_trigger_refresh_with_other_actions(self, refresh_mock):
        owner = OwnerFactory(service="github")

        for event in [GitHubWebhookEvents.INSTALLATION, GitHubWebhookEvents.INSTALLATION_REPOSITORIES]:
            response = self._post_event_data(
                event=event,
                data={
                    "installation": {
                        "id": 11,
                        "account": {
                            "id": owner.service_id,
                            "login": owner.username
                        }
                    },
                    "action": "added"
                }
            )

        refresh_mock.assert_has_calls([
            call(
                ownerid=owner.ownerid,
                username=owner.username,
                sync_teams=False,
                sync_repos=True,
                using_integration=True
            ),
            call(
                ownerid=owner.ownerid,
                username=owner.username,
                sync_teams=False,
                sync_repos=True,
                using_integration=True
            ),
        ])

    def test_membership_with_removed_action_removes_user_from_org(self):
        org = OwnerFactory(service_id='4321')
        user = OwnerFactory(organizations=[org.ownerid], service_id='12')

        response = self._post_event_data(
            event=GitHubWebhookEvents.ORGANIZATION,
            data={
                "action": "member_removed",
                "membership": {
                    "user": {
                        "id": user.service_id
                    }
                },
                "organization": {
                    "id": org.service_id
                }
            }
        )

        user.refresh_from_db()

        assert org.ownerid not in user.organizations