import string
from textwrap import dedent
import shlex
import subprocess
import copy
from __future__ import unicode_literals

from leapcast.environment import Environment
from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol
import tornado.ioloop
import tornado.web
import tornado.websocket
from leapcast.services.websocket import App


class LEAP(tornado.web.RequestHandler):
    application_status = dict(
        name="",
        state="stopped",
        link="",
        pid=None,
        connectionSvcURL="",
        protocols="",
        app=None
    )
    service = """<?xml version="1.0" encoding="UTF-8"?>
    <service xmlns="urn:dial-multiscreen-org:schemas:dial">
        <name>$name</name>
        <options allowStop="true"/>
        <activity-status xmlns="urn:chrome.google.com:cast">
            <description>Legacy</description>
        </activity-status>
        <servicedata xmlns="urn:chrome.google.com:cast">
            <connectionSvcURL>$connectionSvcURL</connectionSvcURL>
            <protocols>$protocols</protocols>
        </servicedata>
        <state>$state</state>
        $link
    </service>
    """

    ip = None
    url = "$query"
    protocols = ""

    def get_name(self):
        return self.__class__.__name__

    def get_status_dict(self):
        status = copy.deepcopy(self.application_status)
        status["name"] = self.get_name()
        return status

    def prepare(self):
        self.ip = self.request.host

    def get_app_status(self):
        return Environment.global_status.get(self.get_name(), self.get_status_dict())

    def set_app_status(self, app_status):

        app_status["name"] = self.get_name()
        Environment.global_status[self.get_name()] = app_status

    def _response(self):
        self.set_header("Content-Type", "application/xml")
        self.set_header(
            "Access-Control-Allow-Method", "GET, POST, DELETE, OPTIONS")
        self.set_header("Access-Control-Expose-Headers", "Location")
        self.set_header("Cache-control", "no-cache, must-revalidate, no-store")
        self.finish(self._toXML(self.get_app_status()))

    @tornado.web.asynchronous
    def post(self, sec):
        """Start app"""
        self.clear()
        self.set_status(201)
        self.set_header("Location", self._getLocation(self.get_name()))
        status = self.get_app_status()
        if status["pid"] is None:
            status["state"] = "running"
            status["link"] = """<link rel="run" href="web-1"/>"""
            status["pid"] = self.launch(self.request.body)
            status["connectionSvcURL"] = "http://%s/connection/%s" % (
                self.ip, self.get_name())
            status["protocols"] = self.protocols
            status["app"] = App.get_instance(sec)

        self.set_app_status(status)
        self.finish()

    @tornado.web.asynchronous
    def get(self, sec):
        """Status of an app"""
        self.clear()
        if self.get_app_status()["pid"]:
            # app crashed or closed
            if self.get_app_status()["pid"].poll() is not None:
                status = self.get_status_dict()
                status["state"] = "stopped"
                status["link"] = ""
                status["pid"] = None

                self.set_app_status(status)
        self._response()

    @tornado.web.asynchronous
    def delete(self, sec):
        """Close app"""
        self.clear()
        self.destroy(self.get_app_status()["pid"])
        status = self.get_status_dict()
        status["state"] = "stopped"
        status["link"] = ""
        status["pid"] = None

        self.set_app_status(status)
        self._response()

    def _getLocation(self, app):
        return "http://%s/apps/%s/web-1" % (self.ip, app)

    def launch(self, data):
        appurl = string.Template(self.url).substitute(query=data)
        if not Environment.fullscreen:
            appurl = '--app="%s"' % appurl
        command_line = """%s --incognito --no-first-run --kiosk --user-agent="%s"  %s""" % (
            Environment.chrome, Environment.user_agent, appurl)
        args = shlex.split(command_line)
        return subprocess.Popen(args)

    def destroy(self, pid):
        if pid is not None:
            pid.terminate()

    def _toXML(self, data):
        return string.Template(dedent(self.service)).substitute(data)

    @classmethod
    def toInfo(cls):
        data = copy.deepcopy(cls.application_status)
        data["name"] = cls.__name__
        data = Environment.global_status.get(cls.__name__, data)
        return string.Template(dedent(cls.service)).substitute(data)
