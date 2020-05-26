from agents import RandomAgent, MCTSAgent
from intuition_model import UnopinionatedValue, UniformPolicy
from dataclasses import dataclass
from itertools import combinations
from trueskill import Rating, quality_1vs1, rate_1vs1
import copy
import random
import tictactoe
import typing


def test_trueskill():
    # Defaults to ...
    agent_1_rating = Rating(100)
    agent_2_rating = Rating(100)
    print(agent_1_rating)
    print(agent_2_rating)

    p_draw = quality_1vs1(agent_1_rating, agent_2_rating)
    print("quality P(draw)?:", p_draw)

    # play game, assume agent_1 wins
    for i in range(20):
        agent_1_rating, agent_2_rating = rate_1vs1(agent_1_rating, agent_2_rating, drawn=True)
        print(agent_1_rating)
        print(agent_2_rating)

        p_draw = quality_1vs1(agent_1_rating, agent_2_rating)
        print("quality P(draw)?:", p_draw)


@dataclass
class MatchupHistory:
    opponent: str
    wins: int = 0
    draws: int = 0
    losses: int = 0

    def games_played(self):
        return self.wins + self.draws + self.losses

    def win_rate(self, draw_weight=0.0):
        return (self.wins + (draw_weight * self.draws)) / self.games_played()

    def loss_rate(self):
        return self.losses / self.games_played()

    def draw_rate(self):
        return self.draws / self.games_played()

    def record(self):
        pct_record = f"{int(round(self.win_rate() * 100, 0))}%-{int(round(self.loss_rate() * 100, 0))}%-{int(round(self.draw_rate() * 100, 0))}%"
        return f"{self.wins}-{self.losses}-{self.draws}  {pct_record}"

    def handle_outcome(self, outcome):
        if outcome == 1:
            self.wins += 1
        elif outcome == 0:
            self.draws += 1
        elif outcome == -1:
            self.losses += 1
        else:
            raise KeyError(f"Unhandleable outcome: {outcome}")


@dataclass
class Entrant:
    bot: typing.Any
    skill_rating: typing.Any = None
    matchup_histories: typing.Any = None

    def __post_init__(self):
        self.skill_rating = Rating()
        self.matchup_histories = {}

    def handle_outcome(self, opponent_entrant, outcome):
        # Update skill rating
        # XXX: Todo

        # Update opponent match history stats
        opponent_name = opponent_entrant.bot.name
        if opponent_name not in self.matchup_histories:
            self.matchup_histories[opponent_name] = MatchupHistory(opponent_name)
        self.matchup_histories[opponent_name].handle_outcome(outcome)


@dataclass
class Bot:
    name: str
    agent_class: typing.Any
    agent_settings: typing.Any


@dataclass
class Tournament:
    entrants: typing.Dict[str, typing.Any]
    environment: typing.Any

    @classmethod
    def setup(cls, environment, bots):
        '''
        :environment is environment class used for game
        :bots is list of Bot that will compete in tournament
        '''
        entrants = {}
        for bot in bots:
            entrants[bot.name] = Entrant(bot)

        return cls(
            entrants=entrants,
            environment=environment,
        )

    def play_single_game(self, entrant_1, entrant_2):
        env = self.environment()

        agent_1 = entrant_1.bot.agent_class(environment=env, **entrant_1.bot.agent_settings)
        agent_2 = entrant_2.bot.agent_class(environment=env, **entrant_2.bot.agent_settings)

        env.add_agent(agent_1)
        env.add_agent(agent_2)

        outcomes = env.run()
        return outcomes

    def head_to_head(self, num_games=100):
        # H2H is just a specific round robin case
        assert len(self.entrants) == 2, "H2H only works with 2 entrants"
        self.round_robin(num_games=num_games)

    def round_robin(self, num_games=100):
        entrants = list(self.entrants.values())
        matchups = list(combinations(entrants, 2))
        for matchup in matchups:
            for i, game_num in enumerate(range(num_games)):
                # Take turns being p1/p2
                players = [matchup[0], matchup[1]]
                if i % 2 == 0:
                    players = [matchup[1], matchup[0]]

                outcomes = self.play_single_game(*players)

                self.handle_game_outcome(players, outcomes)

    def handle_game_outcome(self, players, outcomes):
        # Update skill rating
        # - First player passed to rate_1vs1 is the winner
        p1 = players[0]
        p2 = players[1]
        if outcomes[0] == 0:
            # Draw, order doesn't matter
            p1_new, p2_new = rate_1vs1(p1.skill_rating, p2.skill_rating, drawn=True)
        elif outcomes[0] == 1:
            # P1 won
            p1_new, p2_new = rate_1vs1(p1.skill_rating, p2.skill_rating)
        else:
            # P2 won
            p2_new, p1_new = rate_1vs1(p2.skill_rating, p1.skill_rating)
        p1.skill_rating = p1_new
        p2.skill_rating = p2_new

        # Update stats
        for entrant, outcome in zip(players, outcomes):
            opponent_entrant = [p for p in players if p != entrant][0]
            entrant.handle_outcome(opponent_entrant, outcome)

    def ladder(self, num_rounds):
        entrants = list(self.entrants.values())
        for round_num in range(num_rounds):
            # Sort by skill level
            entrants.sort(key=lambda x: x.skill_rating.mu)

            # For every entrant, play 3 games: the 2 players that are closest above/below you, and
            # one random opponent to play against.  If you're the lowest-ranked player, play the
            # person above you twice.  If you're the highest-ranked player, play the person below
            # you twice.
            # XXX: Better way to matchmake?
            for i in range(len(entrants)):
                matchups = []
                if i == 0:
                    matchups = [
                        [entrants[i], entrants[i + 1]],
                        [entrants[i], entrants[i + 1]],
                    ]
                elif i == (len(entrants) - 1):
                    matchups = [
                        [entrants[i], entrants[i - 1]],
                        [entrants[i], entrants[i - 1]],
                    ]
                else:
                    matchups = [
                        [entrants[i], entrants[i - 1]],
                        [entrants[i], entrants[i + 1]],
                    ]
                matchups.append([
                    entrants[i],
                    random.choice([x for x in entrants if x != entrants[i]]),
                ])

                for matchup in matchups:
                    # Randomly choose who gets to be p1/p2
                    # - Shuffles in place
                    players = [matchup[0], matchup[1]]
                    random.shuffle(players)

                    outcomes = self.play_single_game(*players)

                    self.handle_game_outcome(players, outcomes)

    def display_results(self):
        # Print table of win rates (order by descending)
        table_contents = []
        for entrant in self.entrants.values():
            for other_entrant in self.entrants.values():
                if other_entrant == entrant:
                    continue
                vs_str = f"{entrant.bot.name} v. {other_entrant.bot.name}"
                if other_entrant.bot.name not in entrant.matchup_histories:
                    record = "0-0-0"
                else:
                    record = entrant.matchup_histories[other_entrant.bot.name].record()
                table_contents.append((vs_str, record))

        # Order by name
        print()
        print()
        print("{:<60}{:>30}".format("BOT", "RECORD"))
        table_contents.sort(key=lambda x: x[0].split(" v. ")[0], reverse=True)
        for vs_str, record in table_contents:
            print("{:<60}{:>30}".format(vs_str, record))

        # Print table of skill_rating (order by descending skill)
        table_contents = []
        for entrant in self.entrants.values():
            table_contents.append((entrant.bot.name, entrant.skill_rating.mu, entrant.skill_rating.sigma))
        print()
        print("{:<60}{:>30}{:>30}".format("BOT", "SKILL", "SIGMA"))
        table_contents.sort(key=lambda x: x[1], reverse=True)
        for name, skill, sigma in table_contents:
            print("{:<60}{:>30}{:>30}".format(name, round(skill, 2), round(sigma, 2)))


def test():
    # Setup bots
    mcts_base_settings = dict(
        game_tree=None,
        current_node=None,
        feature_extractor=tictactoe.generate_features,
        value_model=UnopinionatedValue(),
        policy_model=UniformPolicy(),
        move_consideration_steps=200,
        move_consideration_time=None,
        puct_explore_factor=1.0,
        puct_noise_alpha=0.2,
        puct_noise_influence=0.25,
    )
    mcts_agent_unopinionated_settings = copy.deepcopy(mcts_base_settings) # XXX: Better way to copy?

    import intuition_model # noqa
    naive_value_model = intuition_model.NaiveValue()
    naive_value_model.load("./ttt_naive_value.model")

    naive_policy_model = intuition_model.NaivePolicy(tictactoe.Environment().all_possible_actions())
    naive_policy_model.load("./ttt_naive_policy.model")

    mcts_agent_naive_settings = copy.deepcopy(mcts_base_settings)
    mcts_agent_naive_settings["value_model"] = naive_value_model
    mcts_agent_naive_settings["policy_model"] = naive_policy_model

    mcts_agent_naive_slightly_limited_settings = copy.deepcopy(mcts_base_settings)
    mcts_agent_naive_slightly_limited_settings["value_model"] = naive_value_model
    mcts_agent_naive_slightly_limited_settings["policy_model"] = naive_policy_model
    mcts_agent_naive_slightly_limited_settings["move_consideration_steps"] = 100

    bots = [
        Bot(
            "random",
            RandomAgent,
            {},
        ),
        Bot(
            "mcts_naive",
            MCTSAgent,
            mcts_agent_naive_settings,
        ),
        Bot(
            "mcts_naive_slightly_limited",
            MCTSAgent,
            mcts_agent_naive_slightly_limited_settings,
        ),
        Bot(
            "mcts_unopinionated",
            MCTSAgent,
            mcts_agent_unopinionated_settings,
        ),
    ]

    tournament = Tournament.setup(
        environment=tictactoe.Environment,
        bots=bots,
    )
    # tournament.round_robin(num_games=200)
    for i in range(100):
        tournament.ladder(num_rounds=1)
        tournament.display_results()
