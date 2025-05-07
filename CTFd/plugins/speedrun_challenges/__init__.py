from datetime import datetime, timedelta

from flask import Blueprint

from CTFd.exceptions.challenges import (
    ChallengeUpdateException,
    ChallengeCreateException,
)
from CTFd.models import Challenges, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.plugins.migrations import upgrade
from CTFd.utils.user import is_admin


class SpeedrunChallengeModel(Challenges):
    __mapper_args__ = {"polymorphic_identity": "speedrun"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    start_time = db.Column(db.DateTime, default=datetime(year=2030, month=1, day=1))
    end_time = db.Column(db.DateTime, default=datetime(year=2030, month=1, day=2))
    hint1 = db.Column(db.String(255), nullable=True)
    hint2 = db.Column(db.String(255), nullable=True)
    hint1_release_minutes = db.Column(db.Integer, default=0)
    hint2_release_minutes = db.Column(db.Integer, default=0)

    def __init__(self, *args, **kwargs):
        super(SpeedrunChallengeModel, self).__init__(**kwargs)
        self.value = 1


class RedactedResponseDict(dict):
    def __setitem__(self, key, value):
        if key in ("files", "tags", "hints"):
            value = []
        elif key in ("description", "attribution", "connection_info"):
            value = ""
        return super().__setitem__(key, value)


class OverrideHintsDict(dict):
    def __setitem__(self, key, value):
        if key == "hints":
            return
        if key == "lolthatshints":
            key = "hints"
        return super().__setitem__(key, value)

    def actual_set_hints(self, value):
        self["lolthatshints"] = value


class SpeedrunChallenge(BaseChallenge):
    id = "speedrun"  # Unique identifier used to register challenges
    name = "speedrun"  # Name of a challenge type
    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        "create": "/plugins/speedrun_challenges/assets/create.html",
        "update": "/plugins/speedrun_challenges/assets/update.html",
        "view": "/plugins/speedrun_challenges/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/speedrun_challenges/assets/create.js",
        "update": "/plugins/speedrun_challenges/assets/update.js",
        "view": "/plugins/speedrun_challenges/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/speedrun_challenges/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "speedrun_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = SpeedrunChallengeModel

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = SpeedrunChallengeModel.query.filter_by(id=challenge.id).first()
        data = super().read(challenge)
        data.update(
            {
                "start_time": int(challenge.start_time.timestamp()),
                "end_time": int(challenge.end_time.timestamp()),
                "hint1_release_minutes": challenge.hint1_release_minutes,
                "hint2_release_minutes": challenge.hint2_release_minutes,
            }
        )
        if is_admin():
            data.update(
                {
                    "hint1": challenge.hint1,
                    "hint2": challenge.hint2,
                }
            )
            return data
        now = datetime.now()
        if now < challenge.start_time:
            # redact challenge information for unstarted challenges
            data["description"] = (
                f"Challenge starts in {(challenge.start_time - now).total_seconds()} seconds."
            )
            data["attribution"] = data["connection_info"] = ""
            data = RedactedResponseDict(data)
            return data
        hints = []
        if challenge.hint1:
            hint1_release_time = challenge.start_time + timedelta(
                minutes=challenge.hint1_release_minutes
            )
            if now >= hint1_release_time:
                hint1_text = f"Hint 1: {challenge.hint1}"
            else:
                hint1_text = f"Hint 1 unlocks in {(hint1_release_time - now).total_seconds()} seconds."
            hints.append(
                {
                    "id": 998,
                    "cost": 0,
                    "title": "Hint 1",
                    "content": hint1_text,
                }
            )
        if challenge.hint2:
            hint2_release_time = challenge.start_time + timedelta(
                minutes=challenge.hint2_release_minutes
            )
            if now >= hint2_release_time:
                hint2_text = f"Hint 2: {challenge.hint2}"
            else:
                hint2_text = f"Hint 2 unlocks in {(hint2_release_time - now).total_seconds()} seconds."
            hints.append(
                {
                    "id": 999,
                    "cost": 0,
                    "title": "Hint 2",
                    "content": hint2_text,
                }
            )
        if now < challenge.end_time and challenge.end_time - now < timedelta(days=2):
            hints.append(
                {
                    "id": 1000,
                    "cost": 0,
                    "title": "End countdown",
                    "content": f"Challenge ends in {(challenge.end_time - now).total_seconds()} seconds.",
                }
            )
        data = OverrideHintsDict(data)
        data.actual_set_hints(hints)
        return data

    @classmethod
    def create(cls, request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """
        data = request.form or request.get_json()
        for key in data.keys():
            if key in ("hint1_release_minutes", "hint2_release_minutes"):
                try:
                    data[key] = int(data[key])
                except (ValueError, TypeError):
                    raise ChallengeCreateException(f"Invalid input for '{key}'")
            elif key in ("start_time", "end_time"):
                try:
                    data[key] = datetime.fromtimestamp(int(data[key]))
                except (ValueError, TypeError):
                    raise ChallengeCreateException(f"Invalid input for '{key}'")

        challenge = cls.challenge_model(**data)

        db.session.add(challenge)
        db.session.commit()

        return challenge

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()

        for attr, value in data.items():
            # We need to set these to floats so that the next operations don't operate on strings
            if attr in ("hint1_release_minutes", "hint2_release_minutes"):
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    raise ChallengeUpdateException(f"Invalid input for '{attr}'")
            if attr in ("start_time", "end_time"):
                try:
                    value = datetime.fromtimestamp(int(value))
                except (ValueError, TypeError):
                    raise ChallengeUpdateException(f"Invalid input for '{attr}'")
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge

    @classmethod
    def attempt(cls, challenge, request):
        now = datetime.now()
        if now < challenge.start_time:
            return False, "Not started yet"
        elif now > challenge.end_time:
            return False, "Challenge ended, can't submit flag"
        return super().attempt(challenge, request)


def load(app):
    app.db.create_all()
    upgrade(plugin_name="speedrun_challenges")
    CHALLENGE_CLASSES["speedrun"] = SpeedrunChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/speedrun_challenges/assets/"
    )
