/** State port: isolates feature controllers from the rendering runtime. */
export class ComponentStore {
  constructor(component) {
    this.component = component;
  }
  get state() {
    return this.component.state;
  }
  initialize(state) {
    this.component.state = state;
  }
  update = (patch, done) => this.component.setState(patch, done);
}
