import copy
from collections import OrderedDict

from couler.core import pyfunc
from couler.core.constants import OVERWRITE_GPU_ENVS
from couler.core.templates.artifact import OssArtifact
from couler.core.templates.output import OutputArtifact, OutputJob
from couler.core.templates.secret import Secret
from couler.core.templates.template import Template


class Container(Template):
    def __init__(
        self,
        name,
        image,
        command,
        args=None,
        env=None,
        secret=None,
        resources=None,
        image_pull_policy=None,
        retry=None,
        timeout=None,
        pool=None,
        output=None,
        input=None,
        enable_ulogfs=True,
        daemon=False,
        volume_mounts=None,
    ):
        Template.__init__(
            self,
            name=name,
            output=pyfunc.make_list_if_not(output),
            input=pyfunc.make_list_if_not(input),
            timeout=timeout,
            retry=retry,
            pool=pool,
            enable_ulogfs=enable_ulogfs,
            daemon=daemon,
        )
        self.image = image
        self.command = pyfunc.make_list_if_not(command)
        self.args = args
        self.env = env
        self.secret = secret
        self.resources = resources
        self.image_pull_policy = image_pull_policy
        self.volume_mounts = volume_mounts

    def to_dict(self):
        template = Template.to_dict(self)
        # Inputs
        parameters = []
        if self.args is not None:
            i = 0
            for arg in self.args:
                if not isinstance(self.args[i], OutputArtifact):
                    if isinstance(arg, OutputJob):
                        for _ in range(3):
                            parameters.append(
                                {
                                    "name": pyfunc.input_parameter_name(
                                        self.name, i
                                    )
                                }
                            )
                            i += 1
                    else:
                        para_name = pyfunc.input_parameter_name(self.name, i)
                        parameters.append({"name": para_name})
                        i += 1

        # Input
        # Case 1: add the input parameter
        if len(parameters) > 0:
            template["inputs"] = OrderedDict()
            template["inputs"]["parameters"] = parameters

        # Case 2: add the input artifact
        if self.input is not None:
            _input_list = []
            for o in self.input:
                if isinstance(o, OssArtifact):
                    _input_list.append(o.to_yaml())
                if isinstance(o, OutputArtifact):
                    _input_list.append(o.artifact)

            if len(_input_list) > 0:
                if "inputs" not in template:
                    template["inputs"] = OrderedDict()

                template["inputs"]["artifacts"] = _input_list

        # Container
        if not pyfunc.gpu_requested(self.resources):
            if self.env is None:
                self.env = {}
            self.env.update(OVERWRITE_GPU_ENVS)
        template["container"] = self.container_dict()

        # Output
        if self.output is not None:
            _output_list = []
            for o in self.output:
                _output_list.append(o.to_yaml())

            if isinstance(o, OssArtifact):
                # Require only one kind of output type
                template["outputs"] = {"artifacts": _output_list}
            else:
                template["outputs"] = {"parameters": _output_list}

        return template

    def container_dict(self):
        # Container part
        container = OrderedDict({"image": self.image, "command": self.command})
        if pyfunc.non_empty(self.args):
            container["args"] = self._convert_args_to_input_parameters(
                self.args
            )
        if pyfunc.non_empty(self.env):
            container["env"] = pyfunc.convert_dict_to_env_list(self.env)
        if self.secret is not None:
            if not isinstance(self.secret, Secret):
                raise ValueError(
                    "Parameter secret should be an instance of Secret"
                )
            if self.env is None:
                container["env"] = self.secret.to_env_list()
            else:
                container["env"].extend(self.secret.to_env_list())
        if self.resources is not None:
            container["resources"] = {
                "requests": self.resources,
                # To fix the mojibake issue when dump yaml for one object
                "limits": copy.deepcopy(self.resources),
            }
        if self.image_pull_policy is not None:
            container["imagePullPolicy"] = pyfunc.config_image_pull_policy(
                self.image_pull_policy
            )
        if self.volume_mounts is not None:
            container["volumeMounts"] = [
                vm.to_dict() for vm in self.volume_mounts
            ]
        return container

    def _convert_args_to_input_parameters(self, args):
        parameters = []
        if args is not None:
            for i in range(len(args)):
                o = args[i]
                if isinstance(o, OutputArtifact):
                    para_name = o.artifact["name"]
                    parameters.append('"{{inputs.artifacts.%s}}"' % para_name)
                else:
                    para_name = pyfunc.input_parameter_name(self.name, i)
                    parameters.append('"{{inputs.parameters.%s}}"' % para_name)

        return parameters