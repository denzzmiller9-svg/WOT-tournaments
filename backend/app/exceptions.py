

class TournamentNotFoundError(Exception):
    pass


class ForbiddenTournamentError(Exception):
    pass


class AlreadyParticipatingError(Exception):
    pass


class RecruitmentClosedError(Exception):
    pass


class SuperuserParticipantError(Exception):
    pass


class AnotheActiveTournamentError(Exception):
    pass


class AlreadyInvitedError(Exception):
    pass
