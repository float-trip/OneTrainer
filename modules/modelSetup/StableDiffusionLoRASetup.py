from typing import Iterable

import torch
from torch.nn import Parameter

from modules.model.StableDiffusionModel import StableDiffusionModel
from modules.modelSetup.BaseStableDiffusionSetup import BaseStableDiffusionSetup
from modules.module.LoRAModule import LoRAModuleWrapper
from modules.util import create
from modules.util.TrainProgress import TrainProgress
from modules.util.args.TrainArgs import TrainArgs


class StableDiffusionLoRASetup(BaseStableDiffusionSetup):
    def __init__(
            self,
            train_device: torch.device,
            temp_device: torch.device,
            debug_mode: bool,
    ):
        super(StableDiffusionLoRASetup, self).__init__(
            train_device=train_device,
            temp_device=temp_device,
            debug_mode=debug_mode,
        )

    def create_parameters(
            self,
            model: StableDiffusionModel,
            args: TrainArgs,
    ) -> Iterable[Parameter]:
        params = list()

        if args.train_text_encoder:
            params += list(model.text_encoder_lora.parameters())

        if args.train_unet:
            params += list(model.unet_lora.parameters())

        return params

    def create_parameters_for_optimizer(
            self,
            model: StableDiffusionModel,
            args: TrainArgs,
    ) -> Iterable[Parameter] | list[dict]:
        param_groups = list()

        if args.train_text_encoder:
            lr = args.text_encoder_learning_rate if args.text_encoder_learning_rate is not None else args.learning_rate
            param_groups.append({
                'params': model.text_encoder_lora.parameters(),
                'lr': lr,
                'initial_lr': lr,
            })

        if args.train_unet:
            lr = args.unet_learning_rate if args.unet_learning_rate is not None else args.learning_rate
            param_groups.append({
                'params': model.unet_lora.parameters(),
                'lr': lr,
                'initial_lr': lr,
            })

        return param_groups

    def setup_model(
            self,
            model: StableDiffusionModel,
            args: TrainArgs,
    ):
        if model.text_encoder_lora is None:
            model.text_encoder_lora = LoRAModuleWrapper(
                model.text_encoder, args.lora_rank, "lora_te", args.lora_alpha
            )

        if model.unet_lora is None:
            model.unet_lora = LoRAModuleWrapper(
                model.unet, args.lora_rank, "lora_unet", args.lora_alpha, ["attentions"]
            )

        model.text_encoder.requires_grad_(False)
        model.unet.requires_grad_(False)
        model.vae.requires_grad_(False)

        train_text_encoder = args.train_text_encoder and (model.train_progress.epoch < args.train_text_encoder_epochs)
        model.text_encoder_lora.requires_grad_(train_text_encoder)

        train_unet = args.train_unet and (model.train_progress.epoch < args.train_unet_epochs)
        model.unet_lora.requires_grad_(train_unet)

        model.text_encoder_lora.hook_to_module()
        model.unet_lora.hook_to_module()

        if args.rescale_noise_scheduler_to_zero_terminal_snr:
            model.rescale_noise_scheduler_to_zero_terminal_snr()
            model.force_v_prediction()

        model.optimizer = create.create_optimizer(
            self.create_parameters_for_optimizer(model, args), model.optimizer_state_dict, args
        )
        del model.optimizer_state_dict

        model.ema = create.create_ema(
            self.create_parameters(model, args), model.ema_state_dict, args
        )
        del model.ema_state_dict

        self.setup_optimizations(model, args)

    def setup_eval_device(
            self,
            model: StableDiffusionModel
    ):
        model.text_encoder.to(self.train_device)
        model.vae.to(self.train_device)
        model.unet.to(self.train_device)
        if model.depth_estimator is not None:
            model.depth_estimator.to(self.temp_device)

        if model.text_encoder_lora is not None:
            model.text_encoder_lora.to(self.train_device)

        if model.unet_lora is not None:
            model.unet_lora.to(self.train_device)

        model.text_encoder.eval()
        model.vae.eval()
        model.unet.eval()

    def setup_train_device(
            self,
            model: StableDiffusionModel,
            args: TrainArgs,
    ):
        model.text_encoder.to(self.train_device)
        model.vae.to(self.train_device if self.debug_mode else self.temp_device)
        model.unet.to(self.train_device)
        if model.depth_estimator is not None:
            model.depth_estimator.to(self.temp_device)

        if model.text_encoder_lora is not None:
            model.text_encoder_lora.to(self.train_device)

        if model.unet_lora is not None:
            model.unet_lora.to(self.train_device)

        model.text_encoder.train()
        model.vae.eval()
        model.unet.train()

    def after_optimizer_step(
            self,
            model: StableDiffusionModel,
            args: TrainArgs,
            train_progress: TrainProgress
    ):
        train_text_encoder = args.train_text_encoder and (model.train_progress.epoch < args.train_text_encoder_epochs)
        model.text_encoder_lora.requires_grad_(train_text_encoder)

        train_unet = args.train_unet and (model.train_progress.epoch < args.train_unet_epochs)
        model.unet_lora.requires_grad_(train_unet)
