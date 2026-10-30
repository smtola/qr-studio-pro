from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (QSizePolicy, QCheckBox, QLabel, QLineEdit, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget)

from .state import AppState
from .widgets import combo, form, muted, set_combo, set_value, spin

TYPES = [("Website URL", "url"), ("Plain text", "text"), ("E-mail", "email"), ("Phone number", "phone"),
         ("SMS message", "sms"), ("Wi-Fi network", "wifi"), ("Contact card (vCard)", "vcard"),
         ("Map location", "geo"), ("Calendar event", "event"), ("WhatsApp chat", "whatsapp"),
         ("Telegram link", "telegram")]
ECC = [("L – Low (~7% recovery)", "L"), ("M – Medium (~15%)", "M"), ("Q – Quartile (~25%)", "Q"),
       ("H – High (~30%)", "H")]


def _line(name: str, ph: str = "") -> QLineEdit:
    e = QLineEdit()
    e.setAccessibleName(name)
    e.setPlaceholderText(ph)
    return e


class ContentPanel(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        c = state.settings.content
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.type = combo("Content type", TYPES)
        lay.addWidget(self.type)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.url = _line("Website URL", "https://example.com")
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Plain text to encode")
        self.text.setPlaceholderText("Any text – Unicode and Khmer are supported")
        self.text.setFixedHeight(96)
        self.email_to, self.email_subject = _line("E-mail address", "name@example.com"), _line("Subject")
        self.email_body = _line("Message")
        self.phone = _line("Phone number", "+855 12 345 678")
        self.sms_number, self.sms_message = _line("SMS number", "+855 12 345 678"), _line("SMS message")
        self.wifi_ssid, self.wifi_password = _line("Wi-Fi network name"), _line("Wi-Fi password")
        self.wifi_security = combo("Wi-Fi security", [("WPA / WPA2 / WPA3", "WPA"), ("WEP", "WEP"),
                                                       ("No password", "NOPASS")])
        self.wifi_hidden = QCheckBox("Hidden network")
        self.vc_name, self.vc_org = _line("Contact name"), _line("Organisation")
        self.vc_phone, self.vc_email, self.vc_url = _line("Contact phone"), _line("Contact e-mail"), _line("Website")

        self.geo_lat, self.geo_lng = _line("Latitude", "11.5564"), _line("Longitude", "104.9282")
        self.ev_title, self.ev_start = _line("Event title"), _line("Event start", "2026-12-31 18:00")
        self.ev_end, self.ev_loc = _line("Event end (optional)", "2026-12-31 20:00"), _line("Event location")
        self.ev_desc = _line("Event description")
        self.wa_number, self.wa_message = _line("WhatsApp number", "+855 12 345 678"), _line("First message")
        self.tg_user = _line("Telegram username", "@mychannel")

        def page(rows: list[tuple[str, QWidget]]) -> QWidget:
            w = QWidget()
            f = form()
            for lab, wid in rows:
                f.addRow(lab, wid) if lab else f.addRow(wid)
            w.setLayout(f)
            return w

        self.stack.addWidget(page([("URL", self.url)]))
        self.stack.addWidget(page([("", self.text)]))
        self.stack.addWidget(page([("To", self.email_to), ("Subject", self.email_subject), ("Body", self.email_body)]))
        self.stack.addWidget(page([("Number", self.phone)]))
        self.stack.addWidget(page([("Number", self.sms_number), ("Message", self.sms_message)]))
        self.stack.addWidget(page([("Network", self.wifi_ssid), ("Security", self.wifi_security),
                                   ("Password", self.wifi_password), ("", self.wifi_hidden)]))
        self.stack.addWidget(page([("Name", self.vc_name), ("Company", self.vc_org), ("Phone", self.vc_phone),
                                   ("E-mail", self.vc_email), ("Website", self.vc_url)]))
        self.stack.addWidget(page([("Latitude", self.geo_lat), ("Longitude", self.geo_lng)]))
        self.stack.addWidget(page([("Title", self.ev_title), ("Starts", self.ev_start), ("Ends", self.ev_end),
                                   ("Location", self.ev_loc), ("Notes", self.ev_desc)]))
        self.stack.addWidget(page([("Number", self.wa_number), ("Message", self.wa_message)]))
        self.stack.addWidget(page([("Username", self.tg_user)]))

        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.setAccessibleName("Content validation message")
        self.error.hide()
        lay.addWidget(self.error)

        f2 = form()
        self.ecc = combo("Error correction level", ECC)
        self.quiet = spin("Quiet zone in modules", 1, 10, " modules")
        f2.addRow("Error correction", self.ecc)
        f2.addRow("Quiet zone", self.quiet)
        lay.addLayout(f2)
        self.ecc_note = muted("")
        lay.addWidget(self.ecc_note)

        edits = {self.url: "url", self.email_to: "email_to", self.email_subject: "email_subject",
                 self.email_body: "email_body", self.phone: "phone", self.sms_number: "sms_number",
                 self.sms_message: "sms_message", self.wifi_ssid: "wifi_ssid", self.wifi_password: "wifi_password",
                 self.vc_name: "vcard_name", self.vc_org: "vcard_org", self.vc_phone: "vcard_phone",
                 self.vc_email: "vcard_email", self.vc_url: "vcard_url", self.geo_lat: "geo_lat",
                 self.geo_lng: "geo_lng", self.ev_title: "event_title", self.ev_start: "event_start",
                 self.ev_end: "event_end", self.ev_loc: "event_location", self.ev_desc: "event_description",
                 self.wa_number: "wa_number", self.wa_message: "wa_message", self.tg_user: "telegram_user"}
        for w, attr in edits.items():
            w.textEdited.connect(lambda t, a=attr: self._set(a, t))
        self.text.textChanged.connect(lambda: self._set("text", self.text.toPlainText()))
        self.type.currentIndexChanged.connect(self._type_changed)
        self.wifi_security.currentIndexChanged.connect(lambda: self._set("wifi_security", self.wifi_security.currentData()))
        self.wifi_hidden.toggled.connect(lambda v: self._set("wifi_hidden", v))
        self.ecc.currentIndexChanged.connect(lambda: self._set("ecc", self.ecc.currentData(), True))
        self.quiet.valueChanged.connect(lambda v: self._set("quiet_zone", v))
        state.loaded.connect(self.refresh)
        self.refresh()

    def _set(self, attr: str, value, refresh: bool = False) -> None:
        setattr(self.state.settings.content, attr, value)
        self.state.edit(refresh=refresh)

    def _show_page(self, i: int) -> None:
        """Size the stack to the visible page only (a QStackedWidget otherwise uses the tallest page)."""
        self.stack.setCurrentIndex(i)
        for k in range(self.stack.count()):
            pg = self.stack.widget(k)
            pg.setSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Preferred if k == i else QSizePolicy.Policy.Ignored)
        self.stack.updateGeometry()
        self.stack.adjustSize()

    def _type_changed(self) -> None:
        self.state.settings.content.type = self.type.currentData()
        self._show_page(self.type.currentIndex())
        self.state.edit()

    def refresh(self) -> None:
        c = self.state.settings.content
        set_combo(self.type, c.type)
        self._show_page(max(self.type.currentIndex(), 0))
        for w, v in ((self.url, c.url), (self.email_to, c.email_to), (self.email_subject, c.email_subject),
                     (self.email_body, c.email_body), (self.phone, c.phone), (self.sms_number, c.sms_number),
                     (self.sms_message, c.sms_message), (self.wifi_ssid, c.wifi_ssid),
                     (self.wifi_password, c.wifi_password), (self.vc_name, c.vcard_name),
                     (self.vc_org, c.vcard_org), (self.vc_phone, c.vcard_phone), (self.vc_email, c.vcard_email),
                     (self.vc_url, c.vcard_url), (self.geo_lat, c.geo_lat), (self.geo_lng, c.geo_lng),
                     (self.ev_title, c.event_title), (self.ev_start, c.event_start), (self.ev_end, c.event_end),
                     (self.ev_loc, c.event_location), (self.ev_desc, c.event_description),
                     (self.wa_number, c.wa_number), (self.wa_message, c.wa_message), (self.tg_user, c.telegram_user)):
            set_value(w, v)
        with QSignalBlocker(self.text):
            if self.text.toPlainText() != c.text:
                self.text.setPlainText(c.text)
        set_combo(self.wifi_security, c.wifi_security)
        set_value(self.wifi_hidden, c.wifi_hidden)
        set_combo(self.ecc, c.ecc)
        set_value(self.quiet, c.quiet_zone)

    def show_status(self, error: str, ecc_used: str | None) -> None:
        self.error.setText(error)
        self.error.setVisible(bool(error))
        chosen = self.state.settings.content.ecc
        if ecc_used and ecc_used != chosen:
            self.ecc_note.setText(f"Level {ecc_used} is used automatically because a centre logo is shown "
                                  "(change this in the Logo section).")
        else:
            self.ecc_note.setText("Higher levels survive more damage but make denser codes.")
