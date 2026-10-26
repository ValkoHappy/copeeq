/** DOM references and transient presentation resources shared by view controllers. */
export class UiResources {
  constructor(React, props, invalidate) {
    this.props = props;
    this.invalidate = invalidate;
    for (const name of [
      "fileInput",
      "sigInput",
      "canvasRef",
      "viewerRef",
      "stageRef",
      "photoRef",
    ]) {
      this[name] = React.createRef();
    }
  }
}
