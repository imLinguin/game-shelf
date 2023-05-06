# gamesdb.py
#
# Copyright 2022-2023 imLinguin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later


from pathlib import Path
import requests

from gi.repository import Gio
from .create_dialog import create_dialog

from .save_cover import save_cover, resize_cover, save_background

cardridges_to_gamesdb_map = {
    "heroic_gog": "gog",
    "heroic_epic": "epic",
    "steam": "steam",
    "itch": "itch",
}


class GamesDBImport:
    def __init__(self, win, games, importer=None):
        self.win = win
        self.importer = importer
        self.exception = None

        def create_func(game):
            def wrapper(task, *_args):
                self.update_cover(task, game)

            return wrapper

        for game in games:
            Gio.Task.new(None, None, self.task_done).run_in_thread(create_func(game))

    def update_cover(self, task, game):
        if not self.importer:
            game.set_loading(1)

        try:
            gamesdb_data = self.get_gamesdb(game.source, game.game_id)
        except requests.exceptions.RequestException:
            task.return_value(game)
            return

        if not gamesdb_data:
            self.exception = f"Unable to get gamesdb data for game {game.game_id}"
            task.return_value(game)
            return

        json_data = gamesdb_data.json()

        cover = json_data["game"].get("vertical_cover")
        background = json_data["game"].get("background")
        if cover:
            cover_url = (
                cover["url_format"].replace("{formatter}", "").replace("{ext}", "jpg")
            )

            res = requests.get(cover_url)
            if res.ok:
                tmp_cover = Gio.File.new_tmp()[0]
                Path(tmp_cover.get_path()).write_bytes(res.content)
                save_cover(
                    self.win, game.game_id, resize_cover(self.win, tmp_cover.get_path())
                )
        res = None
        if background:
            bg_url = (
                background["url_format"]
                .replace("{formatter}", "")
                .replace("{ext}", "jpg")
            )
            res = requests.get(bg_url)
            if res.ok:
                tmp_cover = Gio.File.new_tmp()[0]
                Path(tmp_cover.get_path()).write_bytes(res.content)
                save_background(self.win, game.game_id, Path(tmp_cover.get_path()))

        task.return_value(game)

    def get_gamesdb(self, source: str, game_id: str) -> dict:
        platform = cardridges_to_gamesdb_map.get(source)
        title_id = game_id.split("_")[-1]

        if not platform:
            self.exception = "Unsupported platform"
            return None

        try:
            response = requests.get(
                f"https://gamesdb.gog.com/platforms/{platform}/external_releases/{title_id}"
            )
            print(response, response.request.url)
            if response.ok:
                return response
        except requests.exceptions.RequestException:
            raise

        return None

    def task_done(self, _task, result):
        print("Done GamesDB", self.exception)
        if self.importer:
            self.importer.queue -= 1
            self.importer.done()
            self.importer.gamesdb_exception = self.exception

        if self.exception and not self.importer:
            create_dialog(
                self.win,
                _("Couldn't Connect to GamesdDB"),
                self.exception,
                "open_preferences",
                _("Preferences"),
            ).connect("response", self.response)

        game = result.propagate_value()[-1]
        game.set_loading(-1)
        if self.importer:
            game.save()
        else:
            game.update()

    def response(self, _widget, response):
        if response == "open_preferences":
            self.win.get_application().on_preferences_action(page_name="sgdb")
