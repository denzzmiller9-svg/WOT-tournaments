import { useEffect, useState } from "react";

const API_URL = "/api/v1";

function getStoredToken() {
  return window.localStorage.getItem("access_token");
}

async function getResponseData(response, fallbackMessage) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail ?? fallbackMessage);
  }
  return data;
}

function formatDate(date) {
  if (!date) return "Дата не указана";
  const parsedDate = new Date(date);
  if (Number.isNaN(parsedDate.getTime())) return "Дата не указана";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsedDate);
}

function toLocalDateTimeInput(date) {
  const parsedDate = new Date(date);
  if (Number.isNaN(parsedDate.getTime())) return "";
  parsedDate.setMinutes(parsedDate.getMinutes() - parsedDate.getTimezoneOffset());
  return parsedDate.toISOString().slice(0, 16);
}

function getDefaultTournamentStartDate() {
  return toLocalDateTimeInput(Date.now() + 60 * 60 * 1000);
}

function durationToHours(duration) {
  if (typeof duration === "number") return String(duration / 3600);
  if (typeof duration !== "string") {
    throw new Error("Не удалось определить длительность турнира.");
  }

  const match = duration.match(
    /^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$/,
  );
  if (!match) throw new Error("Не удалось определить длительность турнира.");

  const [, days = "0", hours = "0", minutes = "0", seconds = "0"] = match;
  return String(
    Number(days) * 24
      + Number(hours)
      + Number(minutes) / 60
      + Number(seconds) / 3600,
  );
}

function getNextStatusChange(tournament) {
  const startDate = new Date(tournament.start_date).getTime();
  if (Number.isNaN(startDate)) return null;

  if (tournament.status === "scheduled") {
    return {
      label: "НАБОР НАЧНЁТСЯ ЧЕРЕЗ",
      timestamp: startDate - durationToHours(tournament.recruitment_time) * 60 * 60 * 1000,
    };
  }
  if (tournament.status === "recruiting") {
    return { label: "ТУРНИР НАЧНЁТСЯ ЧЕРЕЗ", timestamp: startDate };
  }
  if (tournament.status === "in_progress") {
    return {
      label: "ТУРНИР ЗАВЕРШИТСЯ ЧЕРЕЗ",
      timestamp: startDate + durationToHours(tournament.tournament_time) * 60 * 60 * 1000,
    };
  }
  return null;
}

function formatCountdown(milliseconds) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const time = [hours, minutes, seconds]
    .map((unit) => String(unit).padStart(2, "0"))
    .join(":");
  return days ? `${days} дн. ${time}` : time;
}

function getMessageStatusLabel(status) {
  const labels = {
    delivered: "ОЖИДАЕТ ОТВЕТА",
    accepted: "ПРИНЯТО",
    no_relevant: "НЕ АКТУАЛЬНО",
    tournament_invite: "ОТКЛОНЕНО",
  };
  return labels[status] ?? status;
}

function TournamentCreatePage({ accessToken, onNavigate, tournamentId = null }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState(getDefaultTournamentStartDate);
  const [recruitmentHours, setRecruitmentHours] = useState("1");
  const [tournamentHours, setTournamentHours] = useState("1");
  const [reward, setReward] = useState("0");
  const [requiredBattleCount, setRequiredBattleCount] = useState("5");
  const [permittedVehicle, setPermittedVehicle] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingTournament, setIsLoadingTournament] = useState(Boolean(tournamentId));

  useEffect(() => {
    if (!tournamentId) return undefined;

    const controller = new AbortController();
    fetch(`${API_URL}/tournaments/${tournamentId}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    })
      .then((response) => getResponseData(response, "Не удалось загрузить турнир."))
      .then((tournament) => {
        if (!tournament.own_tournament || tournament.status !== "scheduled") {
          throw new Error("Редактировать можно только свой запланированный турнир.");
        }
        setName(tournament.name);
        setDescription(tournament.description);
        setStartDate(toLocalDateTimeInput(tournament.start_date));
        setRecruitmentHours(durationToHours(tournament.recruitment_time));
        setTournamentHours(durationToHours(tournament.tournament_time));
        setReward(String(tournament.reward));
        setRequiredBattleCount(String(tournament.required_battle_count));
        setPermittedVehicle(tournament.permitted_vehicle ?? "");
      })
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingTournament(false);
      });

    return () => controller.abort();
  }, [accessToken, tournamentId]);

  async function submitTournament(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(
        tournamentId ? `${API_URL}/tournaments/${tournamentId}` : `${API_URL}/tournaments`,
        {
          method: tournamentId ? "PATCH" : "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: name.trim(),
            description: description.trim(),
            start_date: new Date(startDate).toISOString(),
            recruitment_time: Number(recruitmentHours) * 60 * 60,
            tournament_time: Number(tournamentHours) * 60 * 60,
            reward: Number(reward),
            required_battle_count: Number(requiredBattleCount),
            permitted_vehicle: permittedVehicle.trim(),
          }),
        },
      );
      const tournament = await getResponseData(
        response,
        tournamentId ? "Не удалось сохранить изменения." : "Не удалось создать турнир.",
      );
      onNavigate(`/tournaments/${tournament.id}`);
    } catch (submitError) {
      setError(submitError.message || "Не удалось связаться с сервером.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="tournament-page" aria-labelledby="create-tournament-title">
      <a
        className="back-link"
        href="/tournaments"
        onClick={(event) => {
          event.preventDefault();
          onNavigate("/tournaments");
        }}
      >
        ← ВСЕ ТУРНИРЫ
      </a>
      <div className="page-heading">
        <p className="eyebrow">
          <span className="eyebrow-line" />
          {tournamentId ? "НАСТРОЙКИ СОБЫТИЯ" : "НОВОЕ СОБЫТИЕ"}
        </p>
        <h1 id="create-tournament-title">
          {tournamentId ? "РЕДАКТИРОВАТЬ ТУРНИР" : "СОЗДАТЬ ТУРНИР"}
        </h1>
        <p className="page-description">
          {tournamentId
            ? "Измени параметры запланированного турнира."
            : "Заполни параметры турнира. Он появится в списке после создания."}
        </p>
      </div>

      {isLoadingTournament ? (
        <p className="page-message" role="status">Загружаем турнир...</p>
      ) : error && tournamentId && !name ? (
        <p className="error-message page-error" role="alert">{error}</p>
      ) : <form className="tournament-form" onSubmit={submitTournament}>
        <label className="field-label" htmlFor="tournament-name">Название</label>
        <input
          autoComplete="off"
          className="text-input"
          id="tournament-name"
          maxLength={50}
          onChange={(event) => setName(event.target.value)}
          required
          value={name}
        />

        <label className="field-label" htmlFor="tournament-description">Описание</label>
        <textarea
          className="text-input tournament-textarea"
          id="tournament-description"
          maxLength={500}
          onChange={(event) => setDescription(event.target.value)}
          required
          rows={4}
          value={description}
        />

        <div className="tournament-form-grid">
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-start-date">Дата начала</label>
            <input
              className="text-input"
              id="tournament-start-date"
              onChange={(event) => setStartDate(event.target.value)}
              required
              type="datetime-local"
              value={startDate}
            />
          </div>
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-recruitment-hours">
              Набор участников (часы)
            </label>
            <input
              className="text-input"
              id="tournament-recruitment-hours"
              min="1"
              onChange={(event) => setRecruitmentHours(event.target.value)}
              required
              step="1"
              type="number"
              value={recruitmentHours}
            />
          </div>
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-duration-hours">
              Длительность турнира (часы)
            </label>
            <input
              className="text-input"
              id="tournament-duration-hours"
              min="1"
              onChange={(event) => setTournamentHours(event.target.value)}
              required
              step="1"
              type="number"
              value={tournamentHours}
            />
          </div>
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-reward">Награда</label>
            <input
              className="text-input"
              id="tournament-reward"
              min="0"
              onChange={(event) => setReward(event.target.value)}
              required
              step="1"
              type="number"
              value={reward}
            />
          </div>
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-required-battle-count">
              Количество боёв
            </label>
            <input
              className="text-input"
              id="tournament-required-battle-count"
              min="1"
              onChange={(event) => setRequiredBattleCount(event.target.value)}
              required
              step="1"
              type="number"
              value={requiredBattleCount}
            />
          </div>
          <div className="tournament-form-field">
            <label className="field-label" htmlFor="tournament-permitted-vehicle">
              Разрешённая техника
            </label>
            <input
              className="text-input"
              id="tournament-permitted-vehicle"
              maxLength={50}
              onChange={(event) => setPermittedVehicle(event.target.value)}
              required
              value={permittedVehicle}
            />
          </div>
        </div>

        {error && <p className="error-message" role="alert">{error}</p>}
        <button className="primary-button" disabled={isSubmitting} type="submit">
          {isSubmitting
            ? (tournamentId ? "СОХРАНЯЕМ ИЗМЕНЕНИЯ..." : "СОЗДАЁМ ТУРНИР...")
            : (tournamentId ? "СОХРАНИТЬ ИЗМЕНЕНИЯ" : "СОЗДАТЬ ТУРНИР")}
          <span aria-hidden="true">→</span>
        </button>
      </form>}
    </section>
  );
}

function TournamentListPage({ accessToken, currentUser, onNavigate }) {
  const [tournaments, setTournaments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setError("");

    const headers = currentUser && accessToken
      ? { Authorization: `Bearer ${accessToken}` }
      : {};

    fetch(`${API_URL}/tournaments`, { headers, signal: controller.signal })
      .then((response) => getResponseData(response, "Не удалось загрузить турниры."))
      .then(setTournaments)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [accessToken, currentUser]);

  return (
    <section className="tournament-page" aria-labelledby="tournament-list-title">
      <div className="page-heading">
        <p className="eyebrow"><span className="eyebrow-line" />АРЕНА WOT</p>
        <h1 id="tournament-list-title">ТУРНИРЫ</h1>
        <p className="page-description">
          Выбери турнир, чтобы узнать подробности и посмотреть рейтинг игроков.
        </p>
        {currentUser && accessToken && (
          <a
            className="create-tournament-link"
            href="/tournaments/new"
            onClick={(event) => {
              event.preventDefault();
              onNavigate("/tournaments/new");
            }}
          >
            + СОЗДАТЬ ТУРНИР
          </a>
        )}
      </div>

      {isLoading ? (
        <p className="page-message" role="status">Загружаем турниры...</p>
      ) : error ? (
        <p className="error-message page-error" role="alert">{error}</p>
      ) : tournaments.length === 0 ? (
        <p className="page-message">Пока нет доступных турниров.</p>
      ) : (
        <div className="tournament-grid">
          {tournaments.map((tournament) => (
            <a
              className="tournament-card"
              href={`/tournaments/${tournament.id}`}
              key={tournament.id}
              onClick={(event) => {
                event.preventDefault();
                onNavigate(`/tournaments/${tournament.id}`);
              }}
            >
              <div className="tournament-card-topline">
                <span className="tournament-status">{tournament.status}</span>
                <span className="tournament-card-top-actions">
                  {tournament.is_participating && (
                    <span className="participating-badge">ВЫ УЧАСТВУЕТЕ</span>
                  )}
                  <span className="tournament-card-arrow" aria-hidden="true">↗</span>
                </span>
              </div>
              <h2>{tournament.name}</h2>
              <p>{tournament.description || "Описание турнира пока не добавлено."}</p>
              <div className="tournament-card-meta">
                <span>СТАРТ</span>
                <time dateTime={tournament.start_date}>{formatDate(tournament.start_date)}</time>
              </div>
              <div className="tournament-card-meta">
                <span>НАГРАДА</span>
                <span>{tournament.reward}</span>
              </div>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function TournamentDetailPage({
  tournamentId,
  accessToken,
  currentUser,
  isCheckingAuth,
  onNavigate,
}) {
  const [tournament, setTournament] = useState(null);
  const [isLoadingTournament, setIsLoadingTournament] = useState(true);
  const [tournamentError, setTournamentError] = useState("");
  const [participants, setParticipants] = useState([]);
  const [isLoadingParticipants, setIsLoadingParticipants] = useState(false);
  const [participantsError, setParticipantsError] = useState("");
  const [participationError, setParticipationError] = useState("");
  const [isJoiningTournament, setIsJoiningTournament] = useState(false);
  const [isInvitePanelOpen, setIsInvitePanelOpen] = useState(false);
  const [currentTime, setCurrentTime] = useState(Date.now());

  useEffect(() => {
    const controller = new AbortController();
    setTournament(null);
    setIsLoadingTournament(true);
    setTournamentError("");

    const headers = currentUser && accessToken
      ? { Authorization: `Bearer ${accessToken}` }
      : {};
    fetch(`${API_URL}/tournaments/${tournamentId}`, { headers, signal: controller.signal })
      .then((response) => getResponseData(response, "Не удалось загрузить турнир."))
      .then(setTournament)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setTournamentError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingTournament(false);
      });

    return () => controller.abort();
  }, [accessToken, currentUser, tournamentId]);

  useEffect(() => {
    if (!currentUser || !accessToken) {
      setParticipants([]);
      setParticipantsError("");
      setIsLoadingParticipants(false);
      return undefined;
    }

    const controller = new AbortController();
    setIsLoadingParticipants(true);
    setParticipantsError("");

    fetch(`${API_URL}/tournaments/${tournamentId}/tournament_participants`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    })
      .then((response) => getResponseData(response, "Не удалось загрузить рейтинг."))
      .then(setParticipants)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setParticipantsError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingParticipants(false);
      });

    return () => controller.abort();
  }, [accessToken, currentUser, tournamentId]);

  useEffect(() => {
    const interval = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const nextStatusChange = tournament ? getNextStatusChange(tournament) : null;
  const isAwaitingStatusUpdate = nextStatusChange && currentTime >= nextStatusChange.timestamp;

  useEffect(() => {
    if (!isAwaitingStatusUpdate) return undefined;

    const controller = new AbortController();
    const refreshTournament = async () => {
      try {
        const headers = currentUser && accessToken
          ? { Authorization: `Bearer ${accessToken}` }
          : {};
        const response = await fetch(`${API_URL}/tournaments/${tournamentId}`, {
          headers,
          signal: controller.signal,
        });
        const updatedTournament = await getResponseData(
          response,
          "Не удалось обновить статус турнира.",
        );
        setTournament(updatedTournament);
      } catch (refreshError) {
        if (refreshError.name !== "AbortError") {
          setTournamentError(refreshError.message || "Не удалось обновить статус турнира.");
        }
      }
    };

    const interval = window.setInterval(refreshTournament, 15000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [accessToken, currentUser, isAwaitingStatusUpdate, tournamentId]);

  const rankedParticipants = participants.slice().sort((first, second) => {
    if (first.place == null) return second.place == null ? 0 : 1;
    if (second.place == null) return -1;
    return first.place - second.place;
  });

  async function participate() {
    setParticipationError("");
    setIsJoiningTournament(true);

    try {
      const response = await fetch(
        `${API_URL}/tournaments/${tournamentId}/participate`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        },
      );
      const participation = await getResponseData(
        response,
        "Не удалось зарегистрироваться на турнир.",
      );
      setTournament((currentTournament) => ({
        ...currentTournament,
        is_participating: true,
      }));
      setParticipants((currentParticipants) => (
        currentParticipants.some((participant) => participant.user_id === participation.user_id)
          ? currentParticipants
          : [
              ...currentParticipants,
              {
                user_id: participation.user_id,
                average_damage: null,
                average_experience: null,
                average_destroyed_tanks: null,
                average_wtr: null,
                place: null,
                battle_count: null,
              },
            ]
      ));
    } catch (joinError) {
      setParticipationError(joinError.message || "Не удалось связаться с сервером.");
    } finally {
      setIsJoiningTournament(false);
    }
  }

  return (
    <section className="tournament-page" aria-labelledby="tournament-title">
      <a
        className="back-link"
        href="/tournaments"
        onClick={(event) => {
          event.preventDefault();
          onNavigate("/tournaments");
        }}
      >
        ← ВСЕ ТУРНИРЫ
      </a>

      {isLoadingTournament ? (
        <p className="page-message" role="status">Загружаем турнир...</p>
      ) : tournamentError ? (
        <p className="error-message page-error" role="alert">{tournamentError}</p>
      ) : tournament ? (
        <>
          <div className="tournament-detail-heading">
            <div>
              <p className="eyebrow"><span className="eyebrow-line" />{tournament.status}</p>
              <h1 id="tournament-title">{tournament.name}</h1>
            </div>
            <div className="tournament-detail-actions">
              {tournament.own_tournament && tournament.status === "scheduled" && (
                <button
                  className="secondary-button edit-tournament-button"
                  onClick={() => onNavigate(`/tournaments/${tournamentId}/edit`)}
                  type="button"
                >
                  РЕДАКТИРОВАТЬ
                </button>
              )}
              <div className="detail-start">
                <span>НАЧАЛО ТУРНИРА</span>
                <time dateTime={tournament.start_date}>{formatDate(tournament.start_date)}</time>
              </div>
            </div>
          </div>
          <p className="tournament-description">
            {tournament.description || "Описание турнира пока не добавлено."}
          </p>
          {nextStatusChange && (
            <section className="tournament-countdown" aria-label="Таймер до смены статуса">
              <span className="tournament-info-label">
                {isAwaitingStatusUpdate ? "ОЖИДАЕМ ОБНОВЛЕНИЕ СТАТУСА" : nextStatusChange.label}
              </span>
              {!isAwaitingStatusUpdate && (
                <time
                  className="tournament-countdown-value"
                  dateTime={new Date(nextStatusChange.timestamp).toISOString()}
                >
                  {formatCountdown(nextStatusChange.timestamp - currentTime)}
                </time>
              )}
            </section>
          )}
          <section className="tournament-conditions" aria-labelledby="tournament-conditions-title">
            <div className="tournament-conditions-heading">
              <p className="eyebrow"><span className="eyebrow-line" />ПРАВИЛА</p>
              <h2 id="tournament-conditions-title">УСЛОВИЯ ТУРНИРА</h2>
            </div>
            <dl className="tournament-conditions-grid">
              <div className="tournament-condition">
                <dt>РАЗРЕШЁННАЯ ТЕХНИКА</dt>
                <dd>{tournament.permitted_vehicle || "Не указана"}</dd>
              </div>
              <div className="tournament-condition">
                <dt>НАГРАДА</dt>
                <dd>{tournament.reward}</dd>
              </div>
              <div className="tournament-condition">
                <dt>НЕОБХОДИМО БОЁВ</dt>
                <dd>{tournament.required_battle_count}</dd>
              </div>
              <div className="tournament-condition">
                <dt>АВТОР</dt>
                <dd>
                  {tournament.owner_id != null && tournament.owner_name ? (
                    <a
                      className="tournament-author-link"
                      href={`/users/${tournament.owner_id}`}
                      onClick={(event) => {
                        event.preventDefault();
                        onNavigate(`/users/${tournament.owner_id}`);
                      }}
                    >
                      {tournament.owner_name}
                    </a>
                  ) : (
                    tournament.owner_name || "Не указан"
                  )}
                </dd>
              </div>
              <div className="tournament-condition">
                <dt>ТИП ТУРНИРА</dt>
                <dd>{tournament.tournament_type === "private" ? "Приватный" : "Публичный"}</dd>
              </div>
            </dl>
          </section>
          {currentUser?.id === tournament.owner_id
            && tournament.tournament_type === "private"
            && tournament.status === "recruiting" && (
            <section className="invite-section" aria-label="Приглашения в турнир">
              <button
                aria-expanded={isInvitePanelOpen}
                className="secondary-button invite-toggle"
                onClick={() => setIsInvitePanelOpen((isOpen) => !isOpen)}
                type="button"
              >
                {isInvitePanelOpen ? "ЗАКРЫТЬ СПИСОК" : "ПРИГЛАСИТЬ"}
              </button>
              {isInvitePanelOpen && (
                <InvitePlayersPanel
                  accessToken={accessToken}
                  currentUser={currentUser}
                  tournamentId={tournamentId}
                />
              )}
            </section>
          )}
          <section className="participation-panel" aria-label="Участие в турнире">
            {isCheckingAuth ? (
              <p className="page-message" role="status">Проверяем авторизацию...</p>
            ) : !currentUser ? (
              <>
                <p>Войдите в аккаунт, чтобы участвовать в турнире.</p>
                <button className="primary-button login-prompt-button" onClick={() => onNavigate("/")}>
                  ВОЙТИ В АККАУНТ <span aria-hidden="true">→</span>
                </button>
              </>
            ) : tournament.is_participating ? (
              <p className="participation-confirmation" role="status">
                ✓ ВЫ УЧАСТВУЕТЕ В ЭТОМ ТУРНИРЕ
              </p>
            ) : !currentUser.wg_account_id ? (
              <>
                <p>Для участия привяжите аккаунт Wargaming.</p>
                <button className="secondary-button link-wg-button" onClick={() => onNavigate("/")}>
                  ПРИВЯЗАТЬ WARGAMING
                </button>
              </>
            ) : tournament.status !== "recruiting" ? (
              <p className="page-message">Регистрация на этот турнир сейчас закрыта.</p>
            ) : (
              <button
                className="primary-button participate-button"
                disabled={isJoiningTournament}
                onClick={participate}
                type="button"
              >
                {isJoiningTournament ? "РЕГИСТРИРУЕМ..." : "УЧАСТВОВАТЬ В ТУРНИРЕ"}
                <span aria-hidden="true">→</span>
              </button>
            )}
            {participationError && (
              <p className="error-message" role="alert">{participationError}</p>
            )}
          </section>
          <section className="leaderboard" aria-labelledby="leaderboard-title">
            <div className="leaderboard-heading">
              <div>
                <p className="eyebrow"><span className="eyebrow-line" />РЕЗУЛЬТАТЫ</p>
                <h2 id="leaderboard-title">РЕЙТИНГ ИГРОКОВ</h2>
              </div>
            </div>

            {isCheckingAuth ? (
              <p className="page-message" role="status">Проверяем авторизацию...</p>
            ) : !currentUser ? (
              <div className="login-prompt">
                <p>Войдите в аккаунт, чтобы посмотреть рейтинг участников.</p>
                <button className="primary-button login-prompt-button" onClick={() => onNavigate("/")}>
                  ВОЙТИ В АККАУНТ <span aria-hidden="true">→</span>
                </button>
              </div>
            ) : isLoadingParticipants ? (
              <p className="page-message" role="status">Загружаем рейтинг...</p>
            ) : participantsError ? (
              <p className="error-message page-error" role="alert">{participantsError}</p>
            ) : rankedParticipants.length === 0 ? (
              <p className="page-message">В турнире пока нет участников.</p>
            ) : (
              <div className="table-wrap">
                <table className="leaderboard-table">
                  <thead>
                    <tr>
                      <th scope="col">МЕСТО</th>
                      <th scope="col">ИГРОК</th>
                      <th scope="col">СР. УРОН</th>
                      <th scope="col">СР. ОПЫТ</th>
                      <th scope="col">УНИЧТОЖЕНО</th>
                      <th scope="col">WTR</th>
                      <th scope="col">БОИ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rankedParticipants.map((participant) => (
                      <tr key={participant.user_id}>
                        <td className="player-place">{participant.place ?? "—"}</td>
                        <td>#{participant.user_id}</td>
                        <td>{participant.average_damage ?? "—"}</td>
                        <td>{participant.average_experience ?? "—"}</td>
                        <td>{participant.average_destroyed_tanks ?? "—"}</td>
                        <td>{participant.average_wtr ?? "—"}</td>
                        <td>{participant.battle_count ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}

function InvitePlayersPanel({ accessToken, currentUser, tournamentId }) {
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [inviteErrors, setInviteErrors] = useState({});
  const [invitedUserIds, setInvitedUserIds] = useState(() => new Set());
  const [sendingUserId, setSendingUserId] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    setError("");

    fetch(`${API_URL}/users`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    })
      .then((response) => getResponseData(response, "Не удалось загрузить список игроков."))
      .then(setUsers)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [accessToken]);

  const filteredUsers = users.filter((user) => (
    user.wg_account_id != null
    && user.id !== currentUser.id
    && user.name.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru"))
  ));

  async function sendInvite(receiverId) {
    setSendingUserId(receiverId);
    setInviteErrors((currentErrors) => ({ ...currentErrors, [receiverId]: "" }));

    try {
      const response = await fetch(`${API_URL}/messages`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          receiver_id: receiverId,
          related_tournament_id: Number(tournamentId),
        }),
      });
      await getResponseData(response, "Не удалось отправить приглашение.");
      setInvitedUserIds((currentIds) => new Set(currentIds).add(receiverId));
    } catch (sendError) {
      setInviteErrors((currentErrors) => ({
        ...currentErrors,
        [receiverId]: sendError.message || "Не удалось связаться с сервером.",
      }));
    } finally {
      setSendingUserId(null);
    }
  }

  return (
    <div className="invite-panel">
      <h2>ПРИГЛАСИТЬ ИГРОКОВ</h2>
      <label className="field-label" htmlFor="invite-player-search">Поиск по имени</label>
      <input
        autoComplete="off"
        className="text-input"
        id="invite-player-search"
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Имя игрока"
        type="search"
        value={search}
      />
      {isLoading ? (
        <p className="page-message" role="status">Загружаем игроков...</p>
      ) : error ? (
        <p className="error-message" role="alert">{error}</p>
      ) : filteredUsers.length === 0 ? (
        <p className="page-message">
          {search ? "Игроки не найдены." : "Нет игроков, которых можно пригласить."}
        </p>
      ) : (
        <ul className="invite-user-list">
          {filteredUsers.map((user) => (
            <li className="invite-user" key={user.id}>
              <span>{user.name}</span>
              <button
                className="secondary-button invite-user-button"
                disabled={invitedUserIds.has(user.id) || sendingUserId === user.id}
                onClick={() => sendInvite(user.id)}
                type="button"
              >
                {invitedUserIds.has(user.id)
                  ? "ОТПРАВЛЕНО"
                  : sendingUserId === user.id
                    ? "ОТПРАВЛЯЕМ..."
                    : "ПРИГЛАСИТЬ"}
              </button>
              {inviteErrors[user.id] && (
                <p className="error-message invite-user-error" role="alert">
                  {inviteErrors[user.id]}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UserProfilePage({ userId, onNavigate }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/users/public/${userId}`, { signal: controller.signal })
      .then((response) => getResponseData(response, "Не удалось загрузить профиль."))
      .then(setUser)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [userId]);

  return (
    <section className="tournament-page" aria-labelledby="user-profile-title">
      <a
        className="back-link"
        href="/tournaments"
        onClick={(event) => {
          event.preventDefault();
          onNavigate("/tournaments");
        }}
      >
        ← ВСЕ ТУРНИРЫ
      </a>
      {isLoading ? (
        <p className="page-message" role="status">Загружаем профиль...</p>
      ) : error ? (
        <p className="error-message page-error" role="alert">{error}</p>
      ) : user ? (
        <>
          <p className="eyebrow"><span className="eyebrow-line" />АВТОР ТУРНИРОВ</p>
          <h1 id="user-profile-title">{user.name}</h1>
        </>
      ) : null}
    </section>
  );
}

function MessagesPage({ accessToken, currentUser, isCheckingAuth, onNavigate }) {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [acceptingMessageId, setAcceptingMessageId] = useState(null);
  const [acceptErrors, setAcceptErrors] = useState({});

  useEffect(() => {
    if (!currentUser || !accessToken) {
      setMessages([]);
      setIsLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError("");

    fetch(`${API_URL}/messages`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      signal: controller.signal,
    })
      .then((response) => getResponseData(response, "Не удалось загрузить сообщения."))
      .then(setMessages)
      .catch((loadError) => {
        if (loadError.name !== "AbortError") {
          setError(loadError.message || "Не удалось связаться с сервером.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [accessToken, currentUser]);

  async function acceptInvite(message) {
    setAcceptingMessageId(message.id);
    setAcceptErrors((currentErrors) => ({ ...currentErrors, [message.id]: "" }));

    try {
      const response = await fetch(
        `${API_URL}/tournaments/${message.related_tournament_id}/participate`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        },
      );
      await getResponseData(response, "Не удалось принять приглашение.");
      setMessages((currentMessages) => currentMessages.map((currentMessage) => (
        currentMessage.id === message.id
          ? { ...currentMessage, status: "accepted" }
          : currentMessage
      )));
    } catch (acceptError) {
      setAcceptErrors((currentErrors) => ({
        ...currentErrors,
        [message.id]: acceptError.message || "Не удалось связаться с сервером.",
      }));
    } finally {
      setAcceptingMessageId(null);
    }
  }

  return (
    <section className="tournament-page messages-page" aria-labelledby="messages-title">
      <p className="eyebrow"><span className="eyebrow-line" />ВХОДЯЩИЕ</p>
      <h1 id="messages-title">СООБЩЕНИЯ</h1>
      {isCheckingAuth ? (
        <p className="page-message" role="status">Проверяем авторизацию...</p>
      ) : !currentUser ? (
        <div className="login-prompt messages-login-prompt">
          <p>Войдите в аккаунт, чтобы посмотреть свои сообщения.</p>
          <button className="primary-button login-prompt-button" onClick={() => onNavigate("/")}>
            ВОЙТИ В АККАУНТ <span aria-hidden="true">→</span>
          </button>
        </div>
      ) : isLoading ? (
        <p className="page-message" role="status">Загружаем сообщения...</p>
      ) : error ? (
        <p className="error-message page-error" role="alert">{error}</p>
      ) : messages.length === 0 ? (
        <p className="page-message">Сообщений пока нет.</p>
      ) : (
        <ul className="message-list">
          {messages.map((message) => {
            const isInvite = message.msg_type === "tournament_invite";
            const canAcceptInvite = isInvite && message.status === "delivered";

            return (
              <li className="message-card" key={message.id}>
                <div>
                  <p className="message-type">
                    {isInvite ? "ПРИГЛАШЕНИЕ В ТУРНИР" : "СООБЩЕНИЕ"}
                  </p>
                  <p className="message-text">{message.text}</p>
                  {message.related_tournament_id != null && (
                    <button
                      className="message-tournament-link"
                      onClick={() => onNavigate(`/tournaments/${message.related_tournament_id}`)}
                      type="button"
                    >
                      ТУРНИР №{message.related_tournament_id}
                    </button>
                  )}
                </div>
                <span className={`message-status message-status-${message.status}`}>
                  {getMessageStatusLabel(message.status)}
                </span>
                {canAcceptInvite && (
                  <div className="message-action">
                    <button
                      className="primary-button accept-invite-button"
                      disabled={acceptingMessageId === message.id}
                      onClick={() => acceptInvite(message)}
                      type="button"
                    >
                      {acceptingMessageId === message.id
                        ? "ПРИНИМАЕМ..."
                        : "ПРИНЯТЬ ПРИГЛАШЕНИЕ"}
                    </button>
                    {acceptErrors[message.id] && (
                      <p className="error-message" role="alert">{acceptErrors[message.id]}</p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function App() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [authMode, setAuthMode] = useState("login");
  const [registrationToken, setRegistrationToken] = useState("");
  const [wgNickname, setWgNickname] = useState("");
  const [accessToken, setAccessToken] = useState(getStoredToken);
  const [currentUser, setCurrentUser] = useState(null);
  const [isCheckingAuth, setIsCheckingAuth] = useState(Boolean(getStoredToken()));
  const [pathname, setPathname] = useState(window.location.pathname);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const callbackData = new URLSearchParams(window.location.hash.slice(1));
    const token = callbackData.get("access_token");
    const pendingRegistrationToken = callbackData.get("registration_token");
    const nickname = callbackData.get("name");
    const wgLinked = callbackData.get("wg_linked") === "1";
    const tokenToLoad = token ?? getStoredToken();

    if (token) {
      window.localStorage.setItem("access_token", token);
      setAccessToken(token);
      setWgNickname(nickname ?? "");
      if (wgLinked) {
        setStatusMessage("Доступ к аккаунту Wargaming успешно обновлён.");
      }
    } else if (pendingRegistrationToken) {
      setRegistrationToken(pendingRegistrationToken);
      setWgNickname(nickname ?? "");
    }

    if (token || pendingRegistrationToken) {
      window.history.replaceState(null, "", window.location.pathname);
    }

    if (tokenToLoad) {
      setIsCheckingAuth(true);
      loadCurrentUser(tokenToLoad)
        .then(setCurrentUser)
        .catch((profileError) => {
          if (profileError.status === 401) {
            window.localStorage.removeItem("access_token");
            setAccessToken("");
            setCurrentUser(null);
          } else {
            setError(profileError.message);
          }
        })
        .finally(() => setIsCheckingAuth(false));
    } else {
      setIsCheckingAuth(false);
    }
  }, []);

  useEffect(() => {
    function updatePathname() {
      setPathname(window.location.pathname);
    }
    window.addEventListener("popstate", updatePathname);
    return () => window.removeEventListener("popstate", updatePathname);
  }, []);

  function navigate(path) {
    if (window.location.pathname !== path) {
      window.history.pushState(null, "", path);
    }
    setPathname(path);
  }

  async function loadCurrentUser(token) {
    const response = await fetch(`${API_URL}/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json();

    if (!response.ok) {
      const profileError = new Error(data.detail ?? "Не удалось загрузить профиль.");
      profileError.status = response.status;
      throw profileError;
    }

    return data;
  }

  async function saveAccessToken(token) {
    const user = await loadCurrentUser(token);
    window.localStorage.setItem("access_token", token);
    setAccessToken(token);
    setCurrentUser(user);
    setIsCheckingAuth(false);
    setRegistrationToken("");
  }

  async function submitPasswordLogin(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const body = new URLSearchParams({ username, password });
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Не удалось войти. Проверьте данные.");
      }

      await saveAccessToken(data.access_token);
    } catch (loginError) {
      setError(loginError.message || "Не удалось связаться с сервером.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitRegistration(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: username, email, password }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Не удалось создать аккаунт.");
      }

      const loginBody = new URLSearchParams({ username, password });
      const loginResponse = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: loginBody,
      });
      const loginData = await loginResponse.json();

      if (!loginResponse.ok) {
        throw new Error(
          loginData.detail ?? "Аккаунт создан, но выполнить вход не удалось.",
        );
      }

      await saveAccessToken(loginData.access_token);
    } catch (registrationError) {
      setError(registrationError.message || "Не удалось связаться с сервером.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitWargamingRegistration(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_URL}/auth/wargaming/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          registration_token: registrationToken,
          email,
        }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Не удалось завершить регистрацию.");
      }

      await saveAccessToken(data.access_token);
    } catch (registrationError) {
      setError(registrationError.message || "Не удалось связаться с сервером.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function logout() {
    window.localStorage.removeItem("access_token");
    setAccessToken("");
    setCurrentUser(null);
    setIsCheckingAuth(false);
    setWgNickname("");
    setStatusMessage("");
  }

  function startWargamingLogin() {
    window.location.assign(`${API_URL}/auth/wargaming/login`);
  }

  async function startWargamingLink() {
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_URL}/auth/wargaming/link`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail ?? "Не удалось начать привязку аккаунта.");
      }

      window.location.assign(data.authorization_url);
    } catch (linkError) {
      setError(linkError.message || "Не удалось связаться с сервером.");
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="ambient ambient-one" aria-hidden="true" />
      <div className="ambient ambient-two" aria-hidden="true" />

      <header className="topbar">
        <a
          className="brand"
          href="/"
          aria-label="WOT Tournaments — главная"
          onClick={(event) => {
            event.preventDefault();
            navigate("/");
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            W
          </span>
          <span className="brand-name">
            WOT <span>TOURNAMENTS</span>
          </span>
        </a>
        <nav className="topbar-actions" aria-label="Основная навигация">
          <a
            className="tournaments-link"
            href="/tournaments"
            onClick={(event) => {
              event.preventDefault();
              navigate("/tournaments");
            }}
          >
            ТУРНИРЫ <span aria-hidden="true">↗</span>
          </a>
          {currentUser && accessToken && (
            <a
              className="tournaments-link"
              href="/messages"
              onClick={(event) => {
                event.preventDefault();
                navigate("/messages");
              }}
            >
              СООБЩЕНИЯ <span aria-hidden="true">↗</span>
            </a>
          )}
          <div className="topbar-note">
            <span className="status-dot" />
            <span>Арена открыта</span>
          </div>
        </nav>
      </header>

      {pathname === "/" ? (
      <section className="auth-layout" aria-labelledby="page-title">
        <div className="intro">
          <p className="eyebrow">
            <span className="eyebrow-line" />
            ВРЕМЯ ПОКАЗАТЬ СЕБЯ
          </p>
          <h1 id="page-title">
            Твоя игра.
            <br />
            <span>Твои правила.</span>
          </h1>
          <p className="intro-copy">
            Участвуй в турнирах, соревнуйся с другими игроками и докажи, на что
            способен.
          </p>
          <div className="feature-list">
            <div className="feature-item">
              <span className="feature-icon" aria-hidden="true">
                01
              </span>
              <span>Турниры для каждого уровня игры</span>
            </div>
            <div className="feature-item">
              <span className="feature-icon" aria-hidden="true">
                02
              </span>
              <span>Результаты и соперники — в одном месте</span>
            </div>
          </div>
          <div className="decorative-grid" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </div>
          <p className="side-caption">СОБЕРИ СВОЮ КОМАНДУ</p>
        </div>

        <section className="auth-card" aria-label="Авторизация">
          <div className="card-topline">
            <span className="card-label">
              {registrationToken ? "НОВЫЙ АККАУНТ" : "АККАУНТ ИГРОКА"}
            </span>
            <span className="card-index">01 / 01</span>
          </div>

          {accessToken ? (
            <div className="success-state" role="status">
              <div className="success-icon" aria-hidden="true">
                ✓
              </div>
              <h2>
                Ты в игре{currentUser?.name ? `, ${currentUser.name}` : wgNickname ? `, ${wgNickname}` : ""}!
              </h2>
              <p>
                {currentUser?.email ?? "Авторизация прошла успешно."}
              </p>
              {statusMessage && (
                <p className="success-message" role="status">{statusMessage}</p>
              )}
              {currentUser?.wg_account_id ? (
                <>
                  <p className="linked-account">
                    Wargaming привязан · ID {currentUser.wg_account_id}
                  </p>
                  <button
                    className="wg-button link-wg-button"
                    disabled={isSubmitting}
                    onClick={startWargamingLink}
                    type="button"
                  >
                    <span className="wg-mark" aria-hidden="true">W</span>
                    <span>
                      {isSubmitting ? "ПЕРЕХОДИМ..." : "ОБНОВИТЬ АВТОРИЗАЦИЮ WARGAMING"}
                    </span>
                    <span className="button-arrow" aria-hidden="true">↗</span>
                  </button>
                </>
              ) : (
                <button
                  className="wg-button link-wg-button"
                  disabled={isSubmitting}
                  onClick={startWargamingLink}
                  type="button"
                >
                  <span className="wg-mark" aria-hidden="true">W</span>
                  <span>
                    {isSubmitting ? "ПЕРЕХОДИМ..." : "ПРИВЯЗАТЬ WARGAMING"}
                  </span>
                  <span className="button-arrow" aria-hidden="true">↗</span>
                </button>
              )}
              {error && <p className="error-message" role="alert">{error}</p>}
              <button className="secondary-button" onClick={logout} type="button">
                Выйти из аккаунта
              </button>
            </div>
          ) : registrationToken ? (
            <>
              <h2 className="card-title">Почти готово</h2>
              <p className="card-description">
                Аккаунт Wargaming подтверждён
                {wgNickname ? `: ${wgNickname}` : ""}. Укажи email для
                регистрации.
              </p>
              <form className="auth-form" onSubmit={submitWargamingRegistration}>
                <label className="field-label" htmlFor="email">
                  Электронная почта
                </label>
                <input
                  autoComplete="email"
                  className="text-input"
                  id="email"
                  maxLength={50}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@example.com"
                  required
                  type="email"
                  value={email}
                />
                {error && <p className="error-message" role="alert">{error}</p>}
                <button
                  className="primary-button"
                  disabled={isSubmitting}
                  type="submit"
                >
                  {isSubmitting ? "СОХРАНЯЕМ..." : "ЗАВЕРШИТЬ РЕГИСТРАЦИЮ"}
                  <span aria-hidden="true">→</span>
                </button>
              </form>
              <p className="privacy-note">
                Wargaming не передаёт email приложениям. Мы сохраним адрес,
                указанный тобой.
              </p>
            </>
          ) : (
            <>
              <div className="auth-tabs" role="tablist" aria-label="Вход или регистрация">
                <button
                  aria-selected={authMode === "login"}
                  className={`auth-tab${authMode === "login" ? " active" : ""}`}
                  onClick={() => {
                    setAuthMode("login");
                    setError("");
                  }}
                  role="tab"
                  type="button"
                >
                  ВХОД
                </button>
                <button
                  aria-selected={authMode === "register"}
                  className={`auth-tab${authMode === "register" ? " active" : ""}`}
                  onClick={() => {
                    setAuthMode("register");
                    setError("");
                  }}
                  role="tab"
                  type="button"
                >
                  РЕГИСТРАЦИЯ
                </button>
              </div>
              <h2 className="card-title">
                {authMode === "login" ? "С возвращением" : "Создай аккаунт"}
              </h2>
              <p className="card-description">
                {authMode === "login"
                  ? "Войди, чтобы продолжить турнирный путь."
                  : "Создай аккаунт по email и выбери игровой никнейм."}
              </p>

              <button
                className="wg-button"
                onClick={startWargamingLogin}
                type="button"
              >
                <span className="wg-mark" aria-hidden="true">
                  W
                </span>
                <span>ВОЙТИ ЧЕРЕЗ WARGAMING.NET</span>
                <span className="button-arrow" aria-hidden="true">
                  ↗
                </span>
              </button>

              <div className="divider">
                <span />
                <span>
                  {authMode === "login" ? "ИЛИ ПО ЛОГИНУ" : "ИЛИ СОЗДАЙ АККАУНТ"}
                </span>
                <span />
              </div>

              {authMode === "register" ? (
                <form className="auth-form" onSubmit={submitRegistration}>
                  <label className="field-label" htmlFor="username">
                    Игровой никнейм
                  </label>
                  <input
                    autoComplete="username"
                    className="text-input"
                    id="username"
                    maxLength={40}
                    minLength={4}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="От 4 до 40 символов"
                    required
                    value={username}
                  />
                  <label className="field-label" htmlFor="email">
                    Электронная почта
                  </label>
                  <input
                    autoComplete="email"
                    className="text-input"
                    id="email"
                    maxLength={50}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="name@example.com"
                    required
                    type="email"
                    value={email}
                  />
                  <label className="field-label" htmlFor="password">
                    Пароль
                  </label>
                  <input
                    autoComplete="new-password"
                    className="text-input"
                    id="password"
                    maxLength={128}
                    minLength={12}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Не менее 12 символов"
                    required
                    type="password"
                    value={password}
                  />
                  {error && <p className="error-message" role="alert">{error}</p>}
                  <button
                    className="primary-button"
                    disabled={isSubmitting}
                    type="submit"
                  >
                    {isSubmitting ? "СОЗДАЁМ АККАУНТ..." : "ЗАРЕГИСТРИРОВАТЬСЯ"}
                    <span aria-hidden="true">→</span>
                  </button>
                </form>
              ) : (
                <form className="auth-form" onSubmit={submitPasswordLogin}>
                  <label className="field-label" htmlFor="username">
                    Игровой никнейм
                  </label>
                  <input
                    autoComplete="username"
                    className="text-input"
                    id="username"
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="Твой никнейм"
                    required
                    value={username}
                  />

                  <div className="field-heading">
                    <label className="field-label" htmlFor="password">
                      Пароль
                    </label>
                  </div>
                  <input
                    autoComplete="current-password"
                    className="text-input"
                    id="password"
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Введи пароль"
                    required
                    type="password"
                    value={password}
                  />
                  {error && <p className="error-message" role="alert">{error}</p>}
                  <button
                    className="primary-button"
                    disabled={isSubmitting}
                    type="submit"
                  >
                    {isSubmitting ? "ВХОДИМ..." : "ВОЙТИ"}
                    <span aria-hidden="true">→</span>
                  </button>
                </form>
              )}
            </>
          )}
        </section>
      </section>
        ) : pathname === "/tournaments" ? (
          <TournamentListPage
            accessToken={accessToken}
            currentUser={currentUser}
            onNavigate={navigate}
          />
        ) : pathname === "/tournaments/new" ? (
          isCheckingAuth ? (
            <section className="tournament-page">
              <p className="page-message" role="status">Проверяем авторизацию...</p>
            </section>
          ) : currentUser && accessToken ? (
            <TournamentCreatePage accessToken={accessToken} onNavigate={navigate} />
          ) : (
            <section className="tournament-page">
              <a className="back-link" href="/tournaments" onClick={(event) => {
                event.preventDefault();
                navigate("/tournaments");
              }}>
                ← ВСЕ ТУРНИРЫ
              </a>
              <p className="page-message">Войдите в аккаунт, чтобы создать турнир.</p>
              <button className="primary-button login-prompt-button" onClick={() => navigate("/")}>
                ВОЙТИ В АККАУНТ <span aria-hidden="true">→</span>
              </button>
            </section>
          )
        ) : pathname === "/messages" ? (
          <MessagesPage
            accessToken={accessToken}
            currentUser={currentUser}
            isCheckingAuth={isCheckingAuth}
            onNavigate={navigate}
          />
        ) : /^\/users\/\d+\/?$/.test(pathname) ? (
          <UserProfilePage
            onNavigate={navigate}
            userId={pathname.match(/^\/users\/(\d+)\/?$/)[1]}
          />
        ) : /^\/tournaments\/\d+\/edit\/?$/.test(pathname) ? (
          isCheckingAuth ? (
            <section className="tournament-page">
              <p className="page-message" role="status">Проверяем авторизацию...</p>
            </section>
          ) : currentUser && accessToken ? (
            <TournamentCreatePage
              accessToken={accessToken}
              onNavigate={navigate}
              tournamentId={pathname.match(/^\/tournaments\/(\d+)\/edit\/?$/)[1]}
            />
          ) : (
            <section className="tournament-page">
              <a className="back-link" href="/tournaments" onClick={(event) => {
                event.preventDefault();
                navigate("/tournaments");
              }}>
                ← ВСЕ ТУРНИРЫ
              </a>
              <p className="page-message">Войдите в аккаунт, чтобы редактировать турнир.</p>
              <button className="primary-button login-prompt-button" onClick={() => navigate("/")}>
                ВОЙТИ В АККАУНТ <span aria-hidden="true">→</span>
              </button>
            </section>
          )
        ) : /^\/tournaments\/\d+\/?$/.test(pathname) ? (
          <TournamentDetailPage
            accessToken={accessToken}
            currentUser={currentUser}
            isCheckingAuth={isCheckingAuth}
            onNavigate={navigate}
            tournamentId={pathname.match(/^\/tournaments\/(\d+)\/?$/)[1]}
          />
        ) : (
          <section className="tournament-page">
            <h1>СТРАНИЦА НЕ НАЙДЕНА</h1>
            <a className="back-link" href="/" onClick={(event) => {
              event.preventDefault();
              navigate("/");
            }}>
              НА ГЛАВНУЮ
            </a>
          </section>
        )}

      <footer className="footer">
        <span>© 2026 WOT TOURNAMENTS</span>
        <span className="footer-divider" />
        <span>СОЗДАНО ДЛЯ ТЕХ, КТО ИГРАЕТ НА ПОБЕДУ</span>
        <span className="footer-coordinate">48° 12&apos; 00&quot; N&nbsp; 16° 22&apos; 00&quot; E</span>
      </footer>
    </main>
  );
}

export default App;
