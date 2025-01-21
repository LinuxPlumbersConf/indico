import csv
import re
import click

from indico.cli.core import cli_group
from indico.core import signals
from indico.core.db import db

from indico.modules.events import Event
from indico.modules.events.contributions import Contribution
from indico.modules.users.models.users import User

from indico.modules.attachments.models.attachments import Attachment, AttachmentType
from indico.modules.attachments.models.folders import AttachmentFolder
from indico.core.db.sqlalchemy.protection import ProtectionMode


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


def _add_link(event_id, title, user_id, link):
    event = Event.get(event_id)
    contributions = Contribution.query.with_parent(event)
    user = User.get(user_id) if user_id else None

    contribution = None
    for c in contributions:
        if title in c.title:
            contribution = c
            break

    if not contribution:
        click.secho('Contribution with title "%s" does not exist' % title, fg='red')
        return

    folder = AttachmentFolder.get_or_create_default(linked_object=contribution)
    assert folder.object == contribution

    att_data = {
        'protected' : False,
        'acl' : (),
        'title' : 'Video',
        'link_url' : link,
        'protection_mode' : ProtectionMode.inheriting,
    }

    attachment = Attachment(user=user, type=AttachmentType.link, folder=folder)
    attachment.populate_from_dict(att_data, skip={'acl', 'protected'})
    attachment.acl = att_data['acl']

    db.session.commit()
    signals.attachments.attachment_created.send(attachment, user=user)


@cli.command()
@click.option('-e', '--event', 'event_id',
              help='Event ID.')
@click.option('-t', '--title', 'title', required=True,
              help='The title of the contribution to update')
@click.option('-u', '--user', 'user_id', type=int, default=38, metavar='USER_ID',
              help='The user which will be shown on the log')
@click.argument('link')
def add_link(event_id, title, user_id, link):
    _add_link(event_id, title, user_id, link)


def _read_csv(filename):
    csv_fields = [ "Title", "URL" ]
    with open(filename, "r") as file:
        data = list(csv.reader(file, delimiter=","))

    title_split_re = re.compile("(.+?) ?- ?(.*)\"?$", re.IGNORECASE)
    videos = []
    for line in data[1:]:
        video = dict(zip(csv_fields, line))
        m = re.match(title_split_re, video["Title"])
        if m:
            video["Title"] = m.group(1)
            video["Authors"] = m.group(2)
        videos.append(video)

    return videos


@cli.command()
@click.option('-c', '--csv', 'csv_file', help='CSV file.')
@click.option('-e', '--event', 'event_id', default='18', help='Event ID.')
@click.option('-u', '--user', 'user_id', type=int, default=38, metavar='USER_ID',
              help='The user which will be shown on the log')
def link_videos(csv_file, event_id, user_id):
    videos = _read_csv(csv_file)
    for video in videos:
        title = video["Title"]
        link = video["URL"]
        _add_link(event_id, title, user_id, link)
