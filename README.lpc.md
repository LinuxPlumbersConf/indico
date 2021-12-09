## Export old site

* On the old site create a dump of the database:

  ```
  pg_dump -U indico -d indico -f /tmp/indico.sql
  ```

* Archive the web-site data for relevant events

  ```
  cd /opt/indico/archive
  tar czf /tmp/event11.tgz event/11
  ```

* Copy the database and the archived data to the new host

## Build

* Clone this reposiory and switch to lpc/v3.0.3 branch

  ```
  git clone https://github.com/rppt/indico.git
  git checkout lpc/v3.0.3

  ```

* Follow Indico [build guide for v3.0.x](https://docs.getindico.io/en/3.0.x/building/) to build a wheel file.

* Copy the resulting wheel to the host that will run Indico

## Install

* Follow Indico [installation guide for v3.0.x])https://docs.getindico.io/en/3.0.x/installation/production/debian/apache/) up to [5. Install Indico](https://docs.getindico.io/en/3.0.x/installation/production/debian/apache/#install-indico). Replace the very last step (`pip install indico`) with installation of the wheel file

  ```
  pip install /path/to/indico-3.0.3-py3-none-any.whl
  ```

* Continue with [6. Configure Indico](https://docs.getindico.io/en/3.0.x/installation/production/debian/apache/#configure-indico) to create the required directories, setup links and generate the configuration file.

## Import

* Import the database:

  ```
  psql  -d indico -U indico -f /path/to/indico.sql
  ```

* Extract the old site archive:

  ```
  cd /opt/indico/archive/
  tar xzf /path/to/event11.tgz
  ```

## Launch

The same as in [the guide](https://docs.getindico.io/en/3.0.x/installation/production/debian/apache/#launch-indico):

```
systemctl restart apache2.service indico-celery.service indico-uwsgi.service
systemctl enable apache2.service postgresql.service redis-server.service indico-celery.service indico-uwsgi.service

```