import Alpine from "alpinejs";
import dayjs from "dayjs";

import CTFd from "./index";

import { Modal, Tab, Tooltip } from "bootstrap";
import highlight from "./theme/highlight";

function addTargetBlank(html) {
  let dom = new DOMParser();
  let view = dom.parseFromString(html, "text/html");
  let links = view.querySelectorAll('a[href*="://"]');
  links.forEach(link => {
    link.setAttribute("target", "_blank");
  });
  return view.documentElement.outerHTML;
}

window.Alpine = Alpine;

Alpine.store("challenge", {
  data: {
    view: "",
  },
});

// Create a store to hold challenges data
Alpine.store("challenges", {
  challengeViews: {},
});

Alpine.data("Hint", () => ({
  id: null,
  html: null,

  async showHint(event) {
    if (event.target.open) {
      let response = await CTFd.pages.challenge.loadHint(this.id);
      let hint = response.data;
      if (hint.content) {
        this.html = addTargetBlank(hint.html);
      } else {
        let answer = await CTFd.pages.challenge.displayUnlock(this.id);
        if (answer) {
          let unlock = await CTFd.pages.challenge.loadUnlock(this.id);

          if (unlock.success) {
            let response = await CTFd.pages.challenge.loadHint(this.id);
            let hint = response.data;
            this.html = addTargetBlank(hint.html);
          } else {
            event.target.open = false;
            CTFd._functions.challenge.displayUnlockError(unlock);
          }
        } else {
          event.target.open = false;
        }
      }
    }
  },
}));

Alpine.data("Challenge", () => ({
  id: null,
  next_id: null,
  submission: "",
  tab: null,
  solves: null,
  response: null,
  share_url: null,
  max_attempts: 0,
  attempts: 0,

  async init() {
    highlight();
  },

  getStyles() {
    return {};
  },

  async showChallenge() {
    new Tab(this.$el).show();
  },

  async showSolves() {
    this.solves = await CTFd.pages.challenge.loadSolves(this.id);
    this.solves.forEach(solve => {
      solve.date = dayjs(solve.date).format("MMMM Do, h:mm:ss A");
      return solve;
    });
  },

  async submitChallenge() {
    this.response = await CTFd.pages.challenge.submitChallenge(
      this.id,
      this.submission,
    );

    await this.renderSubmissionResponse();
  },

  async renderSubmissionResponse() {
    if (this.response.data.status === "correct") {
      this.submission = "";
      await this.showSolves();
    }

    // Increment attempts counter
    if (this.max_attempts > 0 && this.response.data.status != "already_solved") {
      this.attempts += 1;
    }
  },
}));

Alpine.data("ChallengeBoard", () => ({
  loaded: false,
  challenges: [],
  activeChallengeId: null,
  initialHash: window.location.hash,

  async init() {
    await this.loadChallenges();
    this.loaded = true;

    // After loading, handle initial hash if it exists
    if (this.initialHash) {
      this.handleUrlHash(this.initialHash);
    }
  },

  async loadChallenges() {
    this.challenges = await CTFd.pages.challenges.getChallenges();
    
    // Select default challenge if we don't have a hash
    if (!this.initialHash && this.challenges.length > 0) {
      await this.loadChallenge(this.challenges[0].id);
    }
  },

  async handleUrlHash(hash) {
    if (!hash) return;
    
    const chalHash = decodeURIComponent(hash.substring(1));
    const idx = chalHash.lastIndexOf("-");
    if (idx >= 0) {
      const challengeId = chalHash.slice(idx + 1);
      if (this.challenges.some(c => c.id.toString() === challengeId)) {
        await this.loadChallenge(challengeId);
      } else if (this.challenges.length > 0) {
        // If challenge from hash doesn't exist, load the first challenge
        await this.loadChallenge(this.challenges[0].id);
      }
    }
  },

  async loadChallenge(challengeId) {
    // Update active challenge ID for tab selection
    this.activeChallengeId = challengeId;
    
    // Check if we've already loaded this challenge
    if (!Alpine.store("challenges").challengeViews[challengeId]) {
      await CTFd.pages.challenge.displayChallenge(challengeId, challenge => {
        challenge.data.view = addTargetBlank(challenge.data.view);
        // Store this specific challenge view in our challengeViews store
        Alpine.store("challenges").challengeViews[challengeId] = challenge.data.view;
        // Also update the main challenge store for Alpine bindings
        Alpine.store("challenge").data = challenge.data;
        
        // Update URL hash
        history.replaceState(null, null, `#${challenge.data.name}-${challengeId}`);
        
        // Activate the tab programmatically after content has been loaded
        this.$nextTick(() => {
          const tabEl = document.getElementById(`challenge-tab-${challengeId}`);
          if (tabEl) {
            new Tab(tabEl).show();
          }
        });
      });
    } else {
      // If we've already loaded this challenge, just update the main store
      // with the details for binding data like next_id
      await CTFd.pages.challenge.displayChallenge(challengeId, challenge => {
        Alpine.store("challenge").data = challenge.data;
        
        // Update URL hash
        history.replaceState(null, null, `#${challenge.data.name}-${challengeId}`);
        
        // Activate the tab programmatically
        this.$nextTick(() => {
          const tabEl = document.getElementById(`challenge-tab-${challengeId}`);
          if (tabEl) {
            new Tab(tabEl).show();
          }
        });
      });
    }
  },

  getChallengeView(challengeId) {
    // Retrieve the challenge view HTML from our store
    return Alpine.store("challenges").challengeViews[challengeId] || "";
  }
}));

Alpine.start();
