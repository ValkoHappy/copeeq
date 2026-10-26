/** Each feature owns its timers. Disposing the application cancels every scope. */
class TimerScope {
  constructor() {
    this.timeouts = new Set();
    this.intervals = new Set();
  }
  setTimeout = (callback, delay) => {
    const id = setTimeout(() => {
      this.timeouts.delete(id);
      callback();
    }, delay);
    this.timeouts.add(id);
    return id;
  };
  clearTimeout = (id) => {
    clearTimeout(id);
    this.timeouts.delete(id);
  };
  setInterval = (callback, delay) => {
    const id = setInterval(callback, delay);
    this.intervals.add(id);
    return id;
  };
  clearInterval = (id) => {
    clearInterval(id);
    this.intervals.delete(id);
  };
  dispose() {
    for (const id of this.timeouts) clearTimeout(id);
    for (const id of this.intervals) clearInterval(id);
    this.timeouts.clear();
    this.intervals.clear();
  }
}

export class Scheduler {
  constructor() {
    this.scopes = [];
  }
  scope() {
    const scope = new TimerScope();
    this.scopes.push(scope);
    return scope;
  }
  dispose() {
    for (const scope of this.scopes) scope.dispose();
    this.scopes = [];
  }
}
