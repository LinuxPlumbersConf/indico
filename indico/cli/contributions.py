import csv
import re
import click

from indico.cli.core import cli_group
from indico.core import signals
from indico.core.db import db

from indico.modules.events import Event
from indico.modules.events.contributions import Contribution

@cli_group()
def cli():
    pass

@cli.command(name="list")
@click.argument('event_id', type=int)
def contributions_list(event_id):
    event = Event.get(event_id)
    contributions = Contribution.query.with_parent(event)

    for c in sorted(contributions, key=lambda c: c.friendly_id):
        if c.title == 'break':
            continue
        print("%5s %5s)\t%s" % (c.id, "(" + repr(c.friendly_id), c.title))


@cli.command()
@click.argument('contrib_id', type=int)
def show(contrib_id):
    contribution = Contribution.get(contrib_id)

    if not contribution:
        print("No contribution with id %d" % contrib_id)
        return

    print("= %s =" % contribution.title)
    print("Authors:")
    for p in contribution.person_links:
        is_submitter = "submitter" if p.is_submitter else ""
        is_speaker = "speaker" if p.is_speaker else ""
        email = "<" + p.person.email + ">"
        print("%-25s %-35s %s %s" % (p.person.name, email, is_submitter, is_speaker))
