{
  description = "usdAecoWall: Route K wall drivers and published-body example";
  inputs = {
    toolchain.url = "github:criad-com/usdaeco-toolchain?ref=v0.3.8";
    nixpkgs.follows = "toolchain/nixpkgs";
    core.url = "github:criad-com/usdaeco-core?ref=v0.9.2";
    core.inputs.toolchain.follows = "toolchain";
    core.inputs.nixpkgs.follows = "nixpkgs";
    axis.url = "github:criad-com/usdaeco-axis?ref=v0.1.2";
    axis.inputs.toolchain.follows = "toolchain";
    axis.inputs.core.follows = "core";
    axis.inputs.nixpkgs.follows = "nixpkgs";
    buildup.url = "github:criad-com/usdaeco-buildup?ref=v0.2.1";
    buildup.inputs.toolchain.follows = "toolchain";
    buildup.inputs.core.follows = "core";
    buildup.inputs.nixpkgs.follows = "nixpkgs";
    ifc.url = "github:criad-com/usdaeco-ifc?ref=v0.2.0";
    ifc.flake = false;
    datacentre.url = "github:criad-com/usdaeco-datacentre?ref=v0.4.5";
    datacentre.flake = false;
  };
  outputs = { self, nixpkgs, toolchain, core, axis, buildup, ifc, datacentre }:
    let
      eachSystem = nixpkgs.lib.genAttrs [ "aarch64-darwin" "x86_64-linux" ];
      forSystem = system:
        let
          kit = toolchain.lib.forSystem system;
          pkgs = nixpkgs.legacyPackages.${system};
          corePlugin = core.packages.${system}.default;
          axisPlugin = axis.packages.${system}.default;
          buildupPlugin = buildup.packages.${system}.default;
          deps = [ corePlugin axisPlugin buildupPlugin ];
          schema = (kit.buildCodelessSchema { name = "usdAecoWall"; src = self; inherit deps; }).overrideAttrs (old: {
            postInstall = (old.postInstall or "") + ''
              cp -RL tools/usdaeco_wall "$out/python/"
            '';
          });
          plugins = kit.pluginSet { plugins = [ schema ]; };
          setup = ''
            export TOOLCHAIN_DIR=${toolchain}
            export AECO_CORE_ROOT=${core}
            export AECO_AXIS_ROOT=${axis}
            export AECO_BUILDUP_ROOT=${buildup}
            export AECO_IFC_ROOT=${ifc}
            export AECO_DATACENTRE_ROOT=${datacentre}
            export CORE_PLUGIN_DIR=${corePlugin}/plugins/usdAeco/resources
            export AXIS_PLUGIN_DIR=${axisPlugin}/plugins/usdAecoAxis/resources
            export BUILDUP_PLUGIN_DIR=${buildupPlugin}/plugins/usdAecoBuildUp/resources
          '';
          example = pkgs.writeShellApplication {
            name = "example";
            runtimeInputs = [ kit.pythonEnv kit.usd-dev ];
            text = setup + ''
              cp -R ${self} example-work
              chmod -R u+w example-work
              env -u PYTHONPATH python example-work/examples/datacentre/run.py "$@"
            '';
          };
          render = pkgs.writeShellApplication {
            name = "render";
            runtimeInputs = [ kit.pythonEnv kit.usd-dev ];
            text = setup + ''
              cp -R ${self} render-work
              chmod -R u+w render-work
              env -u PYTHONPATH python render-work/examples/datacentre/run.py "$@"
            '';
          };
        in { inherit kit pkgs schema plugins setup example render; };
    in {
      packages = eachSystem (system: let p = forSystem system; in {
        default = p.schema;
        pluginSet = p.plugins;
      });
      checks = eachSystem (system: let p = forSystem system; in {
        library = p.pkgs.runCommand "usdAecoWall-check" { nativeBuildInputs = [ p.kit.pythonEnv p.kit.usd-dev ]; }
          (p.setup + ''
            cp -R ${self} source
            chmod -R u+w source
            cd source
            env -u PYTHONPATH python check.py
            env -u PYTHONPATH python -m pytest -q
            mkdir -p "$out"
          '');
        structure = p.pkgs.runCommand "usdAecoWall-structure" { nativeBuildInputs = [ p.kit.pythonEnv ]; }
          (p.setup + ''
            env -u PYTHONPATH usdaeco-check structure ${self} \
              --dep "$CORE_PLUGIN_DIR" --dep "$AXIS_PLUGIN_DIR" --dep "$BUILDUP_PLUGIN_DIR"
            mkdir -p "$out"
          '');
      });
      devShells = eachSystem (system: let p = forSystem system; in {
        default = p.pkgs.mkShell {
          packages = [ p.kit.pythonEnv p.kit.usd-dev ];
          shellHook = p.setup + "unset PYTHONPATH";
        };
      });
      apps = eachSystem (system: let p = forSystem system; in {
        example = { type = "app"; program = "${p.example}/bin/example"; };
        render = { type = "app"; program = "${p.render}/bin/render"; };
      });
    };
}
