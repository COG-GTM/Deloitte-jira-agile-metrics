import pytest
import datetime

from .conftest import (
    FauxJIRA as JIRA,
    FauxIssue as Issue,
    FauxChange as Change,
    FauxFieldValue as Value,
)

from .querymanager import QueryManager, IssueSnapshot
from .utils import extend_dict


@pytest.fixture
def jira(custom_fields):
    return JIRA(
        fields=custom_fields,
        issues=[
            Issue(
                "A-1",
                summary="Issue A-1",
                issuetype=Value("Story", "story"),
                status=Value("Backlotg", "backlog"),
                resolution=None,
                created="2018-01-01 01:01:01",
                customfield_001="Team 1",
                customfield_002=Value(None, 30),
                customfield_003=Value(None, ["R2", "R3", "R4"]),
                changes=[
                    # the changes are not in chrnological order, the first
                    # change is intentionally the third
                    # status change. This is intended to test that we manage
                    # get the correct first status change as
                    # the transition from Backlog to Next
                    Change(
                        "2018-01-03 01:01:01",
                        [
                            (
                                "resolution",
                                None,
                                "Closed",
                            ),
                            (
                                "status",
                                "Next",
                                "Done",
                            ),
                        ],
                    ),
                    Change(
                        "2018-01-02 01:01:01",
                        [
                            (
                                "status",
                                "Backlog",
                                "Next",
                            )
                        ],
                    ),
                    Change(
                        "2018-01-02 01:01:01",
                        [
                            (
                                "Team",
                                "Team 2",
                                "Team 1",
                            )
                        ],
                    ),
                    Change(
                        "2018-01-04 01:01:01",
                        [
                            (
                                "resolution",
                                "Closed",
                                None,
                            ),
                            (
                                "status",
                                "Done",
                                "QA",
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


@pytest.fixture
def settings(custom_settings):
    return extend_dict(custom_settings, {})


def test_search(jira, settings):
    qm = QueryManager(jira, settings)
    assert qm.attributes_to_fields == {
        "Team": "customfield_001",
        "Estimate": "customfield_002",
        "Release": "customfield_003",
    }

    issues = qm.find_issues("(filter=123)")
    assert issues == jira._issues


def test_resolve_attribute_value(jira, settings):
    qm = QueryManager(jira, settings)
    issues = qm.find_issues("(filter=123)")

    assert qm.resolve_attribute_value(issues[0], "Team") == "Team 1"
    assert qm.resolve_attribute_value(issues[0], "Estimate") == 30
    assert (
        qm.resolve_attribute_value(issues[0], "Release") == "R3"
    )  # due to known_value


def test_resolve_field_value(jira, settings):
    qm = QueryManager(jira, settings)
    issues = qm.find_issues("(filter=123)")

    assert qm.resolve_field_value(issues[0], "customfield_001") == "Team 1"
    assert qm.resolve_field_value(issues[0], "customfield_002") == 30
    assert (
        qm.resolve_field_value(issues[0], "customfield_003") == "R3"
    )  # due to known_value


def test_iter_changes(jira, settings):
    qm = QueryManager(jira, settings)
    issues = qm.find_issues("(filter=123)")
    changes = list(qm.iter_changes(issues[0], ["status", "Team"]))

    assert changes == [
        IssueSnapshot(
            change="status",
            key="A-1",
            date=datetime.datetime(2018, 1, 1, 1, 1, 1),
            from_string=None,
            to_string="Backlog",
        ),
        IssueSnapshot(
            change="Team",
            key="A-1",
            date=datetime.datetime(2018, 1, 1, 1, 1, 1),
            from_string=None,
            to_string="Team 2",
        ),
        IssueSnapshot(
            change="status",
            key="A-1",
            date=datetime.datetime(2018, 1, 2, 1, 1, 1),
            from_string="Backlog",
            to_string="Next",
        ),
        IssueSnapshot(
            change="Team",
            key="A-1",
            date=datetime.datetime(2018, 1, 2, 1, 1, 1),
            from_string="Team 2",
            to_string="Team 1",
        ),
        IssueSnapshot(
            change="status",
            key="A-1",
            date=datetime.datetime(2018, 1, 3, 1, 1, 1),
            from_string="Next",
            to_string="Done",
        ),
        IssueSnapshot(
            change="status",
            key="A-1",
            date=datetime.datetime(2018, 1, 4, 1, 1, 1),
            from_string="Done",
            to_string="QA",
        ),
    ]


def test_iter_changes_timezones(custom_fields, settings):
    jira = JIRA(
        fields=custom_fields,
        issues=[
            Issue(
                "A-2",
                summary="Issue A-2",
                issuetype=Value("Story", "story"),
                status=Value("QA", "qa"),
                resolution=None,
                created="2018-01-01T01:01:01.000+0000",
                customfield_001="Team 1",
                customfield_002=Value(None, 30),
                customfield_003=Value(None, []),
                changes=[
                    # 08:00 UTC, listed first
                    Change(
                        "2018-01-02T08:00:00.000+0000",
                        [("status", "Next", "QA")],
                    ),
                    # 05:00 UTC, so it sorts first despite the later
                    # wall-clock time
                    Change(
                        "2018-01-02T10:00:00.000+0500",
                        [("status", "Backlog", "Next")],
                    ),
                ],
            )
        ],
    )
    qm = QueryManager(jira, settings)
    issue = qm.find_issues("(filter=123)")[0]
    changes = list(qm.iter_changes(issue, ["status"]))

    assert [(c.from_string, c.to_string, c.date) for c in changes[1:]] == [
        ("Backlog", "Next", datetime.datetime(2018, 1, 2, 10, 0, 0)),
        ("Next", "QA", datetime.datetime(2018, 1, 2, 8, 0, 0)),
    ]
    assert changes[0].to_string == "Backlog"
    assert all(c.date.tzinfo is None for c in changes[1:])
